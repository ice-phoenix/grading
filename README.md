# Grading infrastructure

# Set up

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

flask db init
flask db migrate
flask db upgrade
```

You also **need to** compile [the checker](https://github.com/icfpcontest2019/icfpcontest2019) and place `icfpcontest2019.jar` in the root of this repository.

# Running

```
flask run
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3-management
celery -A app.celery worker --loglevel=info -E -O fair
celery flower -A app.celery --address=127.0.0.1 --port=5555 --basic_auth=admin:password --persistent --natural_time=false
```

# Submit with CURL

```
curl -F 'private_id=cb70e4f1259f3d43' -F 'file=@good.zip' localhost:5000/submit
```

# Ranking generator

Assumes `problems/` contains `sizes.csv`:

```
./rankings.py -p persistent/problems/ -g persistent/grades/ --csv-output ranking.csv --html-output ranking.html
```

# Block checker

```
./block -b <num>
```

The blockchain server-side logic is "event-driven", but for simplicity reasons
there are no timed events. Rather, the server expects periodic `GET` requests at
the `/notify/block_timer` endpoint to trigger timed events (e.g. new block
creation). For example:

```
watch -n5 curl http://localhost:5000/notify/block_timer
```