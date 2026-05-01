require 'open-uri'
require 'net/http'
require 'uri'

# 1. ruby-kernel-open-tainted: bare open() with user input (also CWE-22, CWE-78)
def fetch_one(url)
  open(url).read
end

# 2. ruby-kernel-open-tainted: Kernel.open with non-literal
def fetch_two(params)
  body = Kernel.open(params[:url])
  body.read
end

# 3. ruby-uri-open-tainted: URI.open with user input
def fetch_three(user_input)
  URI.open(user_input).read
end

# 4. ruby-uri-open-tainted: URI(expr).open chain
def fetch_four(target)
  URI(target).open.read
end

# 5. ruby-net-http-get-uri-tainted: Net::HTTP.get(URI(expr))
def fetch_five(url)
  Net::HTTP.get(URI(url))
end

# 6. ruby-net-http-get-uri-tainted: Net::HTTP.get_response(URI.parse(expr))
def fetch_six(url)
  Net::HTTP.get_response(URI.parse(url))
end

# 7. ruby-net-http-get-uri-tainted: Net::HTTP.start with tainted host
def fetch_seven(host)
  Net::HTTP.start(host, 80) { |http| http.get('/').body }
end
