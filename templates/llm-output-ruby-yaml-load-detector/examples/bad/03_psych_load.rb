require "psych"

module Cache
  def self.fetch(key)
    raw = Redis.current.get(key)
    return nil if raw.nil?
    Psych.load(raw)   # cache value comes back as full Ruby objects
  end
end
