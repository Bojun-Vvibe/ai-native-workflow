# Tilde-fence variant

~~~yaml
name: ci  
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
~~~

The `name: ci` line carries trailing spaces inside a `~~~` fence.
