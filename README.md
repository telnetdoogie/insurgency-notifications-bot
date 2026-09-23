# insurgency-notifications-bot
**Bot for notification (Discord etc) of Insurgency:Sandstorm events**

---

This tiny script will watch the logs for Insurgency:Sandstorm dedicated server (in this case, running in a docker container) and notify users in discord or other destinations of events such as player joins from a known set of users, player deaths, team wins, and other relevant information.

### Rev 1 
...just announces known players joining the server. More to come.

> Simplest version is a background shell script that reads the log file.
Later revisions will be a more robust python-based tiny app with configurable regex triggers for event detection.

### Usage

* `./insurgency_wacther.sh -start` - Start in the background.
* `./insurgency_wacther.sh -stop)` - Stop the running script.
* `./insurgency_wacther.sh -status` - Show the current status (running or stopped)
