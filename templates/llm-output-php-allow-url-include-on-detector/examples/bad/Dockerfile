FROM php:8.3-fpm

RUN echo "allow_url_include = On" >> /usr/local/etc/php/php.ini \
 && sed -i 's/^;allow_url_include.*/allow_url_include = 1/' /usr/local/etc/php/php.ini-production
