package main

import (
	"context"
	"database/sql"
	"fmt"
)

func GetUserByName(db *sql.DB, name string) (*sql.Rows, error) {
	return db.Query(fmt.Sprintf("SELECT id, name FROM users WHERE name = '%s'", name))
}

func DeleteUser(db *sql.DB, id int) error {
	_, err := db.Exec(fmt.Sprintf("DELETE FROM users WHERE id = %d", id))
	return err
}

func UpdateRole(ctx context.Context, db *sql.DB, id int, role string) error {
	_, err := db.ExecContext(
		ctx,
		fmt.Sprintf("UPDATE users SET role = '%s' WHERE id = %d", role, id),
	)
	return err
}

func InsertNote(tx *sql.Tx, owner string, body string) error {
	_, err := tx.Exec(fmt.Sprintf(
		"INSERT INTO notes (owner, body) VALUES ('%s', '%s')",
		owner, body,
	))
	return err
}

// Sprintf into QueryRow.
func RoleByID(db *sql.DB, id int) *sql.Row {
	return db.QueryRow(fmt.Sprintf("SELECT role FROM users WHERE id = %d", id))
}

// Concat shape — string literal + variable.
func SearchByTag(db *sql.DB, tag string) (*sql.Rows, error) {
	return db.Query("SELECT * FROM posts WHERE tag = '" + tag + "'")
}

// Concat with QueryRowContext.
func CountByOwner(ctx context.Context, db *sql.DB, owner string) *sql.Row {
	return db.QueryRowContext(
		ctx,
		"SELECT COUNT(*) FROM notes WHERE owner = '"+owner+"'",
	)
}

// Sprintf into Prepare.
func PrepareLookup(db *sql.DB, table string) (*sql.Stmt, error) {
	return db.Prepare(fmt.Sprintf("SELECT * FROM %s WHERE id = $1", table))
}
