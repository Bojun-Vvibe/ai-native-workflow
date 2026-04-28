def safe_parse(s)
  Integer(s)
rescue
  nil
end
