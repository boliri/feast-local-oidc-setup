# Feast local setup

The goal of this tiny project is to provide the necessary tools and configurations to build a local Feature Store
using [feast](https://github.com/feast-dev/feast).

Components used across the setup are spun up as Docker containers in your own machine, thus avoiding extra charges
as opposed to production setups, where the usage of Cloud services as data backends usually is the way to go.

## Description

Feature Stores rely on three core components to do their job:

1. The Feature Registry, which is the single source of truth for features defined and persisted by Data Scientists and Data Engineers.

   The Offline Store and the Online Store, which we will introduce shortly, use these features to determine how to access data stored in an external source in a uniform, standardized way.

2. The Offline Store, which holds large volumes of data known as historical feature values.

3. The Online Store, which holds just the freshest feature values, and provides low-latency read access to these values at inference time.

This project has the ability to spin up a Feature Store built with `feast` and configure:

- A Feature Registry backed by a [PostgreSQL](https://www.postgresql.org/) database.

- An Offline Store that reads historical data from `.parquet` files through [DuckDB](https://duckdb.org/).

- An Online Store that serves the freshest feature values from a [Redis](https://redis.io/) instance.

Aside from spinning up the Feature Store components, it also configures a [Keycloak](https://www.keycloak.org/) instance that
allows their users to mess around with `feast`'s Security Model to prevent unauthorized access to feature values (e.g. PII data) based on RBAC policies.

## Pre-requisites

* Python 3.11+
* [poetry](https://python-poetry.org/docs/#installation)
* [docker](https://docs.docker.com/engine/install/)
* [docker-compose](https://docs.docker.com/compose/install/)

## Setup

> [!TIP]
>
> Setting components up in the same order as shown below is highly recommended.

### Keycloak

To run a Keycloak instance with a pre-configured `master` realm, run `docker compose up --build keycloak` and wait for it to
import the realm configuration from `keycloak/realm-export.json`.

On import success, you should be able to log in to the Keycloak admin console by hitting http://localhost:8080 and submitting
the `admin` user credentials - by default, its password is `admin`. You'll see the `master` realm's landing page, and there
should be a `feature-store` client under the `Clients` section.

> [!IMPORTANT]
>
> The `feature-store` client comes with a custom role named `super-reader` that becomes crucial at the moment that features
> are persisted to the Feature Registry. This role should be assigned to the `admin` user by default, but unfortunately,
> exporting a realm through the Keycloak UI does not export role assignments.
>
> **Do make sure to assign the `super-reader` role to the `admin` user manually** - otherwise, RBAC policies defined later 
> will not be enforced.

### Data backends

To spin up two of the three core components of the Feature Store, run these commands in any order:

* `docker compose up --build registry`
* `docker compose up --build online-store`

You may be wondering: where's the `docker compose` command to spin up the Offline Store? Well, actually there _isn't_ such
command.

DuckDB is an in-process OLAP database engine, so packing and running it inside a Docker container would be kind of
overengineering. In fact, the DuckDB team discourages users from trying to achieve such containerization:

> There is no official DuckDB Docker image available. DuckDB uses an in-process deployment model, where the client
> application and DuckDB are running in the same process. Additionally to the DuckDB clients for Python, R, and other
> programming languages, DuckDB is also available as a standalone command-line client. This client is available on a wide
> range of platforms and is portable without containerization, making it unnecessary to containerize the process for most
> deployments.

Just assume this for now: the Offline Store _exists_, but materializes simply as a system process, and not as a Docker
container.

### Feature servers

Behind the scenes, `feast` uses multiple third-party Python SDKs to talk to data backends, namely
[redis-py](https://github.com/redis/redis-py), [duckdb](https://pypi.org/project/duckdb/), and
[psycopg3](https://www.psycopg.org/). These SDKs are not easily integrable with OIDC tools such as Keycloak, so we need to
rely on a complimentary tool to ensure seamless integration between both worlds (OIDC and databases). Feature servers to the rescue!

A feature server is some kind of proxy with the ability to intercept any feature retrieval issued through the
`FeatureStore::get_historical_features()` or `FeatureStore::get_online_features()` methods of the `feast` SDK for Python.
When intercepted, the RBAC policies attached to the set of requested features are compared to the roles
assigned to the user making the retrieval, and if there's no full match, the request is unauthorized.

There are two feature servers: one for the Offline Store, and another for the Online Store. You can spin them up by running
these commands:

* `docker compose up --build offline-feature-server`
* `docker compose up --build online-feature-server`

### Feature registration

Now that we have all our components running, it is time to register some features to the Registry. To do so, there's a one-off
Docker service in the `compose.yml` file named `register-features`, which will read all the Feast artifacts defined in
`docker/feature-ops/register-features/feature_repo.py` and persist them to the Feature Registry.

The set of artifacts defined are:

* Projects
  * `feastlocal`

* Entities
  * `driver`

* Sources
  * File sources
    * `driver_hourly_stats_source`

  * Request sources
    * `vals_to_add`

  * Push sources
    * `driver_stats_push_source`

* Feature views
  * `driver_hourly_stats`
  * `driver_hourly_stats_fresh`

* On-demand feature views
  * `transformed_conv_rate`
  * `transformed_conv_rate_fresh`

* Feature services
  * `driver_activity_v1`
  * `driver_activity_v2`
  * `driver_activity_v3`

* Permissions (a.k.a. RBAC policies)
  * `reader`

To persist them to the Feature Registry, run `docker compose up --build register-features`. You should see these traces as
the task moves on:

```bash
$ docker compose up --build register-features

register-features-1  | Applying changes for project feastlocal
register-features-1  | Created project feastlocal
register-features-1  | Created entity driver
register-features-1  | Created feature view driver_hourly_stats_fresh
register-features-1  | Created feature view driver_hourly_stats
register-features-1  | Created on demand feature view transformed_conv_rate_fresh
register-features-1  | Created on demand feature view transformed_conv_rate
register-features-1  | Created feature service driver_activity_v1
register-features-1  | Created feature service driver_activity_v2
register-features-1  | Created feature service driver_activity_v3
register-features-1  | Created permission reader
register-features-1  | Created sqlite table feastlocal_driver_hourly_stats_fresh
register-features-1  | Created sqlite table feastlocal_driver_hourly_stats

register-features-1 exited with code 0
```

### Feature materialization

Materialization is a data movement process that copies the freshest feature values from the Offline Store, and writes them
to the Online Store. This movement ensures sub-millisecond data access at inference time in Machine Learning applications.

Just as we registered features, we can run a one-off task to materialize features. You only need to run
`docker compose up --build materialize-features` to spin up the container that will copy data from one source to another.

```bash
$ docker compose up --build materialize-features

materialize-features-1  | Materializing 2 feature views from 1970-01-01 00:00:00+00:00 to 2024-12-31 00:00:00+00:00 into the redis online store.
materialize-features-1  | 
materialize-features-1  | driver_hourly_stats_fresh:
100%|███████████████████████████████████████████████████████████████| 5/5 [00:00<00:00, 1958.31it/s]
materialize-features-1  | driver_hourly_stats:
100%|███████████████████████████████████████████████████████████████| 5/5 [00:00<00:00, 4580.93it/s]

materialize-features-1 exited with code 0
```

That's it! At this point, both the Offline and the Online Stores should be able to serve data on request.

## Retrieving features

Now that the Feature Store is set up, you can retrieve some features to see it in action! To do so, there's a Python script at
`test-feature-retrieval/feature_retrieval.py` that retrieves both historical and online features, and prints them to the standard
output.

> [!IMPORTANT]
>
> There's some weird issue with the Feast SDK expecting you to have an existing `/tmp/feast/data` folder to build the `FeatureStore`
> class instance from the `feature_store.yaml`.
>
> I am not sure why this happens, but just to sidestep this limitation, you can run `mkdir -p /tmp/feast/data` from a terminal.

To run this Python script, you can execute these commands from a terminal:

```bash
cd <path-to-this-repo>/test-feature-retrieval

poetry install
poetry run python feature_retrieval.py
```

You should see an output similar to this:

```bash
Initializing Feature Store...
Feature Store initialized

Fetching historical features... (remember to run `docker-compose up --build register-features` first!)
---- HISTORICAL FEATURES ----
   driver_id           event_timestamp  label_driver_reported_satisfaction  val_to_add  val_to_add_2  conv_rate  acc_rate  avg_daily_trips
0       1001 2021-04-12 10:59:42+00:00                                   1           1            10   0.658415  0.098658              772
1       1002 2021-04-12 08:12:10+00:00                                   5           2            20   0.700783  0.714265              665
2       1003 2021-04-12 16:40:26+00:00                                   3           3            30   0.588724  0.353072              412

Fetching online features... (remember to run `docker-compose up --build materialize-features` first!)
---- ONLINE FEATURES ----
{
    "driver_id": [
        1004,
        1005
    ],
    "acc_rate": [
        0.19152821600437164,
        0.8072004914283752
    ],
    "conv_rate": [
        0.7408708333969116,
        0.16526198387145996
    ],
    "avg_daily_trips": [
        864,
        111
    ]
}

Done!
```

As you can see, the script ran without issues, and we were able to retrieve some features from our Feature Store!

# Architecture

## The big picture

The following diagram gives an idea of how our Feature Store's architecture look like:

![fs-architecture](./docs/static/img/fs-architecture.png)

The goal of this diagram is to outline the feature retrieval workflow from two different perspectives: while
retrieving historical features, and while retrieving online features.

With the Python script we ran before in mind, let's split this diagram and discuss the whole workflow in both scenarios.

## Historical features retrieval

![offline-feature-retrieval](./docs/static/img/offline-feature-retrieval.png)

To fetch historical features from an external source, users and ML apps must invoke the `get_historical_features()`
method from the `FeatureStore` class. In out test script, this class is instantiated by passing the
`test-feature-retrieval/feature_store.yaml` file.

In this scenario, the most relevant bits from that file are these ones:

```yaml
# SQL Registry backed by PostgreSQL
registry:
    registry_type: sql
    path: postgresql+psycopg://postgres:mysecretpassword@localhost:5432/feast

# Remote Offline Store - calls to FeatureStore::get_historical_features will reach an Offline Feature Server under the hood,
# so the user doesn't need to make explicit HTTP calls
offline_store:
    type: remote
    host: localhost # URL of the Offline Feature Server
    port: 8282

# Config for clients of the multiple feature servers - username and password required
auth:
  type: oidc
  client_id: feature-store
  client_secret: lsXQ8rAUBVIkt2eC1WGG3F36w10Tokqv
  username: admin
  password: admin
  auth_discovery_url: http://localhost:8080/realms/master/.well-known/openid-configuration
```

As soon as `get_historical_features()` is invoked, a gRPC message is sent to a proxy layer known as the
[Offline Feature Server](https://docs.feast.dev/reference/feature-servers/offline-feature-server). This piece is an Apache Arrow Flight
server that sits between the consumers of the Offline Store and the Offline Store itself to hide the details of the underlying data
technology backing the store.

When the gRPC message arrives at the Offline Feature Server, the Feast SDK runs some security checks to make sure that the set of
requested features can be read by the user or the ML app. The SDK first asks Keycloak for a new access token using the credentials
specified in the `auth` block of the `feature_store.yaml`, and only if the user account has the expected roles assigned in Keycloak
and included in the access token (as defined in the `Permission` object stored to the Feature Registry), the SDK is allowed to
reach the Offline Store to pull historical features.

Provided the security checks are passed, the feature request arrives at the Offline Store, but before we go deeper into how the request
is resolved...[do you remember we mentioned there's no Docker container for the Offline Store](#data-backends)? Well, the truth is the
Offline Store actually exists, but it's embedded into the Offline Feature Server container.

Offline Stores are traditionally backed by Data Warehouses, which are composed by two fundamental layers: compute and storage. While the
storage layer essentially represents where an organization's data is stored, the compute layer is responsible for resolving the SQL
statements that select, filter and aggregate data from the storage layer for direct consumption. Since DWHs are expensive and typically
bound to Cloud providers such as AWS, GCP or Snowflake (among many others), our best bet to build a local, free Offline Store is to
use DuckDB for the compute layer, and Parquet files embedded as Docker volumes for the storage layer.

So, when the user / ML app-initiated request gets to our Offline Store, the Feast DuckDB plugin will scan the `FileSource`s persisted
to the Registry, take their filesystem path, and load the contents of relevant Parquet files into an in-memory database. After that,
the SDK will extract the set of selected features from the request gRPC message to build a SQL `SELECT` statement, and execute it
against the data from the in-memory database. Finally, the SDK will build a dataframe with the historical features retrieved thanks
to the SQL statement, and will return it to the user / ML app.

## Online features retrieval

![online-feature-retrieval](./docs/static/img/online-feature-retrieval.png)

Similarly to the previous scenario, online features can be retrieved through a proxy server known as the
[Online Feature Server](https://docs.feast.dev/reference/feature-servers/python-feature-server) using the `get_online_features()` method
of the `FeatureStore` class. The dynamics are pretty much the same, with one subtle difference: while the communication between
users / ML apps and the server still happens via HTTP, this server is based on REST instead of gRPC.

These are the relevant bits of the `feature_store.yaml` while pulling online features:

```yaml
# SQL Registry backed by PostgreSQL
registry:
    registry_type: sql
    path: postgresql+psycopg://postgres:mysecretpassword@localhost:5432/feast

# Remote Online Store - calls to FeatureStore::get_online_features will reach an Online Feature Server under the hood,
# so the user doesn't need to make explicit HTTP calls
online_store:
    type: remote
    path: http://localhost:8181 # URL of the Online Feature Server

# Config for clients of the multiple feature servers - username and password required
auth:
  type: oidc
  client_id: feature-store
  client_secret: lsXQ8rAUBVIkt2eC1WGG3F36w10Tokqv
  username: admin
  password: admin
  auth_discovery_url: http://localhost:8080/realms/master/.well-known/openid-configuration
```

When it comes to the Online Store, in this case we _do_ have it isolated on its own container as a Redis instance. There's no need to
mount Docker volumes here, as long as [features have already been materialized](#feature-materialization); the Online Feature Server
will just send Redis commands to the Online Store container based on the selected features specified in the HTTP request made to the
feature server's REST API.

The workflow here is straightforward: the request for online features arrives at the feature server, security policies are
enforced through Feast's Security Layer, and data is ultimately pulled from the Online Store using Redis commands. That's pretty much it.