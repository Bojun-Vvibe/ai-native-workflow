using System.Data.SqlClient;
using System.Data.OracleClient;

public class BadQueries
{
    public void GetUserByName(SqlConnection conn, string name)
    {
        // Finding 1: ctor concat with SELECT.
        var cmd = new SqlCommand("SELECT * FROM users WHERE name = '" + name + "'", conn);
        cmd.ExecuteReader();
    }

    public void GetUserById(SqlConnection conn, int id)
    {
        // Finding 2: ctor interpolation with SELECT + placeholder.
        var cmd = new SqlCommand($"SELECT * FROM users WHERE id = {id}", conn);
        cmd.ExecuteReader();
    }

    public void DeleteUser(SqlConnection conn, string name)
    {
        // Finding 3: CommandText concat with DELETE.
        var cmd = conn.CreateCommand();
        cmd.CommandText = "DELETE FROM users WHERE name = '" + name + "'";
        cmd.ExecuteNonQuery();
    }

    public void UpdateUser(SqlConnection conn, string email, int id)
    {
        // Finding 4: CommandText interpolation with UPDATE.
        var cmd = conn.CreateCommand();
        cmd.CommandText = $"UPDATE users SET email = '{email}' WHERE id = {id}";
        cmd.ExecuteNonQuery();
    }

    public void InsertUser(SqlConnection conn, string name)
    {
        // Finding 5: CommandText string.Format with INSERT.
        var cmd = conn.CreateCommand();
        cmd.CommandText = string.Format("INSERT INTO users (name) VALUES ('{0}')", name);
        cmd.ExecuteNonQuery();
    }

    public void OracleVariant(OracleConnection conn, string name)
    {
        // Finding 6: OracleCommand ctor concat.
        var cmd = new OracleCommand("SELECT * FROM emp WHERE ename = '" + name + "'", conn);
        cmd.ExecuteReader();
    }

    public void VerbatimInterp(SqlConnection conn, string tbl)
    {
        // Finding 7: $@"..." interpolated verbatim with CREATE.
        var cmd = conn.CreateCommand();
        cmd.CommandText = $@"CREATE TABLE {tbl} (id INT)";
        cmd.ExecuteNonQuery();
    }
}
