package example

class Resolver {
  def resolve(name: String): Config = {
    val parts = name.split("\\.")
    if (parts.length < 2) {
      return null
    }
    val cfg = lookup(parts(0))
    if (cfg == null) {
      return null
    }
    cfg
  }

  private def lookup(s: String): Config = new Config(s)
}

class Config(val name: String)
