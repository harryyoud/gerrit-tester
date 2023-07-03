import queue
import json
import logging
import os
import requests
import sys
import threading
import time
#from requests.auth import HTTPBasicAuth

import paramiko


queue = queue.Queue()

logging.basicConfig(level=logging.INFO)
logger = paramiko.util.logging.getLogger()
logger.setLevel(logging.INFO)

options = dict(timeout=60)
try:
    options["username"] = os.environ["GERRIT_USERNAME"]
    options["hostname"] = os.environ["GERRIT_HOSTNAME"]
    options["port"] = int(os.environ["GERRIT_PORT"])
    options["key_filename"] = os.environ["GERRIT_KEYFILE"]
    jenkins_auth = (
        os.environ["JENKINS_USERNAME"],
        os.environ["JENKINS_TOKEN"]
    )
except KeyError:
    print("Environment variables GERRIT_{USERNAME,PASSWORD,PORT,KEYFILE} and JENKINS_{USERNAME,TOKEN} need defining")
    sys.exit(1)


class GerritStream(threading.Thread):
    """Threaded job; listens for Gerrit events and puts them in a queue."""

    def run(self):
        while True:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(**options)
                client.get_transport().set_keepalive(60)
                _, stdout, _ = client.exec_command('gerrit stream-events -s patchset-created')
                for line in stdout:
                    queue.put(json.loads(line))
            except:
                logging.exception('Gerrit error')
            finally:
                client.close()
            time.sleep(5)


# For a description of the JSON structure of events emitted by Gerrit's
# stream-events command, see the Gerrit documentation.
# http://gerrit.googlecode.com/svn/documentation/2.1.2/cmd-stream-events.html

templates = {
    'comment-added':     ('Comment added ({0[author][name]}): "{0[comment]}" '
                          '[{0[change][project]}] - {0[change][url]}'),

    'change-merged':     ('Change merged ({0[submitter][name]}):'
                          '{0[change][subject]} [{0[change][project]}] - '
                          '{0[change][url]}'),

    'patchset-added':    ('Change merged ({0[submitter][name]}):'
                          '{0[change][subject]} [{0[change][project]}] - '
                          '{0[change][url]}'),

    'change-abandoned':  ('Change merged ({0[submitter][name]}):'
                          '{0[change][subject]} [{0[change][project]}] - '
                          '{0[change][url]}'),
}


gerrit = GerritStream()
gerrit.daemon = True
gerrit.start()


example = {
	'uploader': {
		'name': 'Harry Youd',
		'email': 'harry@harryyoud.co.uk',
		'username': 'harryyoud'
	},
	'patchSet': {
		'number': 3,
		'revision': '207039efa0aef7026d695fa6bac3db2ea087cfcf',
		'parents': ['c4a5b2cebc469de2ee4645f8049c4bb37e796bbd'],
		'ref': 'refs/changes/87/212887/3',
		'uploader': {
			'name': 'Harry Youd',
			'email': 'harry@harryyoud.co.uk',
			'username': 'harryyoud'
		},
		'createdOn': 1532872041,
		'author': {
			'name': 'Harry Youd',
			'email': 'harry@harryyoud.co.uk',
			'username': 'harryyoud'
		},
		'kind': 'TRIVIAL_REBASE',
		'sizeInsertions': 7,
		'sizeDeletions': -7
	},
	'change': {
		'project': 'LineageOS/lineage_wiki',
		'branch': 'master',
		'id': 'I07b6b8b877c5d6738c0bc9ce778625776abb087d',
		'number': 212887,
		'subject': '[DNM] Speed up page loads',
		'owner': {
			'name': 'Harry Youd',
			'email': 'harry@harryyoud.co.uk',
			'username': 'harryyoud'
		},
		'url': 'https://review.lineageos.org/212887',
		'commitMessage': '[DNM] Speed up page loads\n\nChange-Id: I07b6b8b877c5d6738c0bc9ce778625776abb087d\n',
		'createdOn': 1523792552,
		'status': 'NEW',
		'private': True
	},
	'project': 'LineageOS/lineage_wiki',
	'refName': 'refs/heads/master',
	'changeKey': {
		'id': 'I07b6b8b877c5d6738c0bc9ce778625776abb087d'
	},
	'type': 'patchset-created',
	'eventCreatedOn': 1532872041
}


test_jenkins_url = "https://jenkins.harryyoud.co.uk/job/{}/buildWithParameters?token=TOKEN_GOES_HERE&CHANGE={}&PATCHSET={}&STATUS={}&SILENT=false"
test_jobs = {"LineageOS/lineage_wiki": "lineage-wiki-preview", "LineageOS/www": "lineage-www-preview", "LineageOS/hudson": "lineage-hudson-validator"}

while True:
    event = queue.get()

    if event['project'] in test_jobs:
        private = 'private' in event['change'] and event['change']['private']
        is_private_str = "private" if private else "public"
        print(f"Event received: {event['change']['status']} change {event['change']['number']}/{event['patchSet']['number']} created on ({event['project']}) ({is_private_str})")
        sys.stdout.flush()

        jenkins_url = test_jenkins_url.format(
		test_jobs[event['project']],
		event['change']['number'],
		event['patchSet']['number'],
		'PRIVATE' if private else 'NEW'
	)

        r = requests.post(jenkins_url, auth=jenkins_auth)
        print(f" => Sent to Jenkins ({r.status_code})")
        sys.stdout.flush()

gerrit.join()
