def load_config(path)
  File.read(path)
rescue Exception
  nil
end
