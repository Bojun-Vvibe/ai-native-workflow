# A bare rescue with a *real* body is not flagged by this detector.
# (Whether you should write this is style; the detector targets the
# truly-empty / nil / false / next-only cases.)
def fetch(url)
  Net::HTTP.get(URI(url))
rescue
  log_failure(url)
  retry_later(url)
end
