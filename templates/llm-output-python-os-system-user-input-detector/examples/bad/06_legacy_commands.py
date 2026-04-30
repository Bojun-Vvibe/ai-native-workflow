# Bad: legacy commands.getoutput with concatenated input. Python 2-era
# pattern that LLMs still emit when porting old code.
import commands  # noqa


def whois(domain):
    return commands.getoutput("whois " + domain)
