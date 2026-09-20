package store

import (
	"database/sql"
	"errors"
	"sort"
)

// Admission order and adoption order differ when input arrives during an active
// request. Publish only derived ranks for the authorized facts; no control table
// or hidden Work/round information enters the read view. The same read transaction
// fixes both the ledger and adoption metadata, and both enter the view identity.
func viewAdvanceOrder(tx *sql.Tx, facts []Event) (map[string]int64, error) {
	rows, err := tx.Query("SELECT id,rowid FROM rounds ORDER BY rowid")
	if err != nil {
		return nil, err
	}
	rounds := map[string]int64{}
	for rows.Next() {
		var id string
		var rank int64
		if err = rows.Scan(&id, &rank); err != nil {
			rows.Close()
			return nil, err
		}
		rounds[id] = rank
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return nil, err
	}
	rows, err = tx.Query("SELECT i.seq,MAX(r.rowid) FROM round_inputs i JOIN rounds r ON r.id=i.round_id GROUP BY i.seq")
	if err != nil {
		return nil, err
	}
	inputs := map[int64]int64{}
	for rows.Next() {
		var seq int64
		var rank int64
		if err = rows.Scan(&seq, &rank); err != nil {
			rows.Close()
			return nil, err
		}
		inputs[seq] = rank
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return nil, err
	}
	result, visible := map[string]int64{}, map[int64]bool{}
	for _, fact := range facts {
		rank := inputs[fact.Seq]
		if fact.Source == "model-adapter" && (fact.Kind == "model.message" || fact.Kind == "tool.result") {
			round, _ := fact.Payload["round_id"].(string)
			rank = rounds[round]
		}
		if rank > 0 {
			result[fact.FactID], visible[rank] = rank, true
		}
	}
	ordered := make([]int64, 0, len(visible))
	for rank := range visible {
		ordered = append(ordered, rank)
	}
	sort.Slice(ordered, func(i, j int) bool { return ordered[i] < ordered[j] })
	dense := map[int64]int64{}
	for i, rank := range ordered {
		dense[rank] = int64(i + 1)
	}
	for fact, rank := range result {
		result[fact] = dense[rank]
	}
	return result, nil
}
