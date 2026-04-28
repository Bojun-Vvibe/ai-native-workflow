def fetch(url)
  begin
    Net::HTTP.get(URI(url))
  rescue Exception => e
    puts "swallowed: #{e}"
    nil
  end
end
