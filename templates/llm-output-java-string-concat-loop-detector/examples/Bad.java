// Bad: builds a String via += inside loops -- O(n^2) and a frequent
// LLM hallucination when asked for "join these into a CSV row".
public class Bad {
    public String csvRow(String[] cells) {
        String row = "";
        for (int i = 0; i < cells.length; i++) {
            row += cells[i];                  // FINDING 1: += in for-loop
            if (i < cells.length - 1) {
                row += ",";                   // FINDING 2: += in for-loop
            }
        }
        return row;
    }

    public String repeat(String unit, int n) {
        String out = "";
        int i = 0;
        while (i < n) {
            out = out + unit;                 // FINDING 3: self-concat in while-loop
            i++;
        }
        return out;
    }

    public String numberLine(int count) {
        String s = "";
        for (int k = 0; k < count; k++) {
            s += k;                           // FINDING 4: += in for-loop (String += int)
        }
        return s;
    }

    public String dump(java.util.List<String> items) {
        String acc = "";
        for (String it : items) {
            acc += it + "\n";                 // FINDING 5: += in for-each loop
        }
        return acc;
    }

    public String nested(String[][] grid) {
        String out = "";
        for (String[] row : grid) {
            for (String cell : row) {
                out += cell;                  // FINDING 6: += in nested loop
            }
            out += "\n";                      // FINDING 7: += in outer loop
        }
        return out;
    }
}
