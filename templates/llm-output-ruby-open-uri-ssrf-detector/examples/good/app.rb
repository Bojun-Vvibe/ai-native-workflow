require 'net/http'
require 'uri'

ALLOWED_HOSTS = %w[api.example.com www.example.com].freeze

# Safe: literal URL fetch
def fetch_literal
  Net::HTTP.get(URI('https://api.example.com/v1/health'))
end

# Safe: explicit literal-host fetch
def fetch_health
  Net::HTTP.start('api.example.com', 443, use_ssl: true) do |http|
    http.get('/v1/health').body
  end
end

# Safe: File.open is unrelated to open-uri (different receiver)
def read_file(path)
  File.open(path, 'r') { |f| f.read }
end

# Safe: IO.open with literal fd
def stdout_dup
  IO.open(1, 'w')
end

# Safe: String literal-only URI.open (fixed target)
def fetch_fixed
  URI.open('https://example.com/robots.txt').read
end

# Safe: suppression marker on a tainted shape we have audited
def fetch_audited(url)
  open(url).read  # llm-allow:ruby-ssrf
end
