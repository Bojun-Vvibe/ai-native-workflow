// String parsing using java.time, no ToolBox involved.
import java.time.LocalDate

object DateUtil {
  def parse(s: String): LocalDate = LocalDate.parse(s)
}
