#!/bin/bash
set -e

echo "Building frank_bot Docker image..."
docker build -t frank_bot:latest /home/seanr/dev/frank_bot

echo "Stopping and removing current frank_bot container on onlogic-closet..."
ssh onlogic-closet "docker stop frank_bot && docker rm frank_bot" || true

echo "Transferring image to onlogic-closet..."
docker save frank_bot:latest | ssh onlogic-closet docker load

echo "Starting new frank_bot container on onlogic-closet..."
ssh onlogic-closet "docker run -d --name frank_bot --env-file /home/frank_bot/.env -p 8000:8000 frank_bot:latest"

echo "Verifying deployment..."
ssh onlogic-closet "docker ps --filter name=frank_bot"

echo "Deployment complete!"
