using System.Data.SqlClient;

public class GoodQueries
{
    // Parameterized constructor — no concat.
    public void GetUserByName(SqlConnection conn, string name)
    {
        var cmd = new SqlCommand("SELECT * FROM users WHERE name = @name", conn);
        cmd.Parameters.AddWithValue("@name", name);
        cmd.ExecuteReader();
    }

    // Parameterized CommandText assignment — literal only.
    public void DeleteUser(SqlConnection conn, string name)
    {
        var cmd = conn.CreateCommand();
        cmd.CommandText = "DELETE FROM users WHERE name = @name";
        cmd.Parameters.AddWithValue("@name", name);
        cmd.ExecuteNonQuery();
    }

    // Interpolation, but no SQL keyword in the string — not flagged.
    public string FormatGreeting(string name)
    {
        return $"Hello, {name}!";
    }

    // Concatenation, but both operands are literals (constant SQL) —
    // not flagged.
    public void StaticSplit(SqlConnection conn)
    {
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT * " + "FROM users";
        cmd.ExecuteReader();
    }

    // Suppressed by allow-marker (rare legitimate dynamic identifier).
    public void TableSwitch(SqlConnection conn, string verifiedTable)
    {
        var cmd = conn.CreateCommand();
        // Verified against allowlist before this point.
        cmd.CommandText = $"SELECT COUNT(*) FROM {verifiedTable}"; // llm-allow:sqlcommand-concat
        cmd.ExecuteScalar();
    }

    // string.Format for non-SQL — not flagged.
    public string Greet(string name)
    {
        return string.Format("Hello, {0}", name);
    }

    // Comment containing fake SQL — must not fire.
    public void Documented(SqlConnection conn)
    {
        // Example for docs: SELECT * FROM users WHERE id = " + id
        var cmd = new SqlCommand("SELECT 1", conn);
        cmd.ExecuteScalar();
    }
}
