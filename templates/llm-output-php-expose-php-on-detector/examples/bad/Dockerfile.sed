FROM php:8.2-fpm
RUN sed -i 's/^expose_php\s*=.*/expose_php = yes/' /usr/local/etc/php/php.ini
