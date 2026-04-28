def safe_parse(s)
  Integer(s)
rescue ArgumentError, TypeError => e
  warn "parse failed: #{e.message}"
  raise
end
