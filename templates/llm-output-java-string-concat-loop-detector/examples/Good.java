// Good: same behavior as Bad.java but uses StringBuilder, so no findings.
public class Good {
    public String csvRow(String[] cells) {
        StringBuilder row = new StringBuilder();
        for (int i = 0; i < cells.length; i++) {
            row.append(cells[i]);
            if (i < cells.length - 1) {
                row.append(",");
            }
        }
        return row.toString();
    }

    public String repeat(String unit, int n) {
        StringBuilder out = new StringBuilder(unit.length() * Math.max(n, 0));
        int i = 0;
        while (i < n) {
            out.append(unit);
            i++;
        }
        return out.toString();
    }

    // Concatenation OUTSIDE a loop is fine -- compiles to one StringBuilder
    // by javac. We must not flag this.
    public String greet(String name) {
        String s = "hello, " + name + "!";
        return s;
    }

    // String += outside any loop -- not flagged.
    public String once(String prefix) {
        String s = prefix;
        s += "-tail";
        return s;
    }

    public String dump(java.util.List<String> items) {
        StringBuilder acc = new StringBuilder();
        for (String it : items) {
            acc.append(it).append('\n');
        }
        return acc.toString();
    }
}
