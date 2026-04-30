package main

import (
	"context"
	"database/sql"
	"fmt"
)

// Parameterized: placeholders, not string-formatted.
func GetUserByNameSafe(db *sql.DB, name string) (*sql.Rows, error) {
	return db.Query("SELECT id, name FROM users WHERE name = $1", name)
}

func DeleteUserSafe(db *sql.DB, id int) error {
	_, err := db.Exec("DELETE FROM users WHERE id = ?", id)
	return err
}

func UpdateRoleSafe(ctx context.Context, db *sql.DB, id int, role string) error {
	_, err := db.ExecContext(
		ctx,
		"UPDATE users SET role = $1 WHERE id = $2",
		role, id,
	)
	return err
}

// fmt.Sprintf is fine when not feeding a SQL execution method (e.g.
// formatting a log line).
func LogQueryAttempt(name string) {
	msg := fmt.Sprintf("attempted lookup for name=%s", name)
	_ = msg
}

// Sprintf used to build a non-SQL string (e.g. URL path) — no SQL
// keyword present in the format string.
func BuildPath(id int) string {
	return fmt.Sprintf("/api/v1/users/%d/profile", id)
}

// Concat used for non-SQL purposes — no SQL keyword present.
func GreetUser(name string) string {
	return "hello, " + name + "!"
}

// Author has audited this branch — explicit suppression.
func AdminTableQuery(db *sql.DB, table string) (*sql.Rows, error) {
	// llm-allow:sprintf-sql-query
	return db.Query(fmt.Sprintf("SELECT * FROM %s", table))
}

// Comment containing what looks like a vulnerable example — must not
// fire because it is inside a comment.
//   db.Query(fmt.Sprintf("SELECT * FROM users WHERE id = %d", id))
func CommentExample() {}

// String literal mentioning the pattern — must not fire.
func StringMention() string {
	return "do NOT write db.Query(fmt.Sprintf(\"SELECT ... %s\", x))"
}
