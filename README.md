# Minotaur

Minotaur is a lightweight task monitoring/reporting service. The name is a silly
play on words.

# Overview

Minotaur allows you to register a job that needs to happen 1+ times. A job has a
unique endpoint. POST to a job's endpoint with a status value (a string no
greater than 256 characters), and Minotaur records an instance of that job
(successful or otherwise).

Minotaur also allows you to set expected status(es) and schedule for a job. For
example, a job is expected to finish with status 'success' at least once a day,
except on weekends.

If a job doesn't get run according to your schedule, it sends you an email.
