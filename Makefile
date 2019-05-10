.PHONY: all
all:

.PHONY: init
init:
	mkdir -p persistent/
	git init persistent/

.PHONY: teams
teams:
	sqlite3 -csv app/app.db "SELECT id, name FROM team;" > persistent/teams.csv
	$(MAKE) -C persistent commit-teams