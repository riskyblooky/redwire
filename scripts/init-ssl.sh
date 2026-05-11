#!/bin/bash

# Configuration
DOMAIN="redwire.yourdomain.com"
EMAIL="admin@yourdomain.com"
STAGING=1 # Set to 1 for testing with Let's Encrypt staging environment

if [ -d "nginx/certbot/conf/live/$DOMAIN" ]; then
  echo "Certificate already exists for $DOMAIN. Skipping initialization."
  exit 0
fi

echo "### Downloading recommended TLS parameters..."
mkdir -p nginx/certbot/conf
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > nginx/certbot/conf/options-ssl-nginx.conf
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > nginx/certbot/conf/ssl-dhparams.pem

echo "### Creating dummy certificate for $DOMAIN..."
path="/etc/letsencrypt/live/$DOMAIN"
mkdir -p "nginx/certbot/conf/live/$DOMAIN"
docker-compose run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:4096 -days 1\
    -keyout \"$path/privkey.pem\" \
    -out \"$path/fullchain.pem\" \
    -subj \"/CN=localhost\"" certbot

echo "### Starting nginx..."
docker-compose up --force-recreate -d nginx

echo "### Deleting dummy certificate for $DOMAIN..."
docker-compose run --rm --entrypoint "\
  rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN" certbot

echo "### Requesting Let's Encrypt certificate for $DOMAIN..."
# Select appropriate email arg
case "$EMAIL" in
  "") email_arg="--register-unsafely-without-email" ;;
  *) email_arg="--email $EMAIL" ;;
esac

# Enable staging mode if needed
if [ $STAGING != "0" ]; then staging_arg="--staging"; fi

docker-compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $email_arg \
    -d $DOMAIN \
    --rsa-key-size 4096 \
    --agree-tos \
    --force-renewal" certbot

echo "### Reloading nginx..."
docker-compose exec nginx nginx -s reload
