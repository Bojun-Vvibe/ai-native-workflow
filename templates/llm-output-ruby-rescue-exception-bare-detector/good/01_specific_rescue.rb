def load_config(path)
  File.read(path)
rescue Errno::ENOENT
  ""
end
