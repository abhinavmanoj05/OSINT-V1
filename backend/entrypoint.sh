#!/bin/bash

# Wait for databases
echo "Waiting for PostgreSQL..."
while ! nc -z postgres 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

echo "Waiting for Neo4j..."
while ! nc -z neo4j 7687; do
  sleep 0.1
done
echo "Neo4j started"

# Run migrations
alembic upgrade head

# Start application
exec "$@"