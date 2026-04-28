package main

import (
	"database/sql"
)

func queryEach(db *sql.DB, ids []int) {
	for _, id := range ids {
		rows, err := db.Query("SELECT 1 WHERE id=?", id)
		if err != nil {
			continue
		}
		defer rows.Close() // BAD: rows pile up
		_ = rows
	}
}
