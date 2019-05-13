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

# Submit with CURL

```
curl -F 'private_id=cb70e4f1259f3d43' -F 'file=@good.zip' localhost:5000/submit
```