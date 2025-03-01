#!/usr/bin/env bash
docker stop postgresql
docker rm postgresql

docker run -d --name postgresql -p 5432:5432 \
-e POSTGRES_PASSWORD=postgres \
-e POSTGRES_USER=postgres \
-e POSTGRES_DB=floword \
postgres:16
