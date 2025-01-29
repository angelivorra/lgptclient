# Servidor robot

## Arrancar app
```
    /home/angel/venvflask/bin/flask --app app run --host=0.0.0.0 --debug
```

## Comando produccion
```
    gunicorn  'app:create_app'
```