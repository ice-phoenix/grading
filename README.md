# Grading infrastructure

# Set up

```
python3 -m venv venv
source venv/bin/activate
pip install python-dotenv flask flask-wtf flask-sqlalchemy flask-migrate celery

flask db init
flask db migrate
flask db upgrade
```

# Running

```
flask run
docker run -d -p 5672:5672 rabbitmq
celery -A app.celery worker --loglevel=info
```