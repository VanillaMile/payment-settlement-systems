CREATE TABLE bank_details (
  primary_routing_transit_number NUMERIC PRIMARY KEY,
  legal_name VARCHAR(256) NOT NULL,
  federal_employer_identification_number NUMERIC,
  master_account_rtn NUMERIC UNIQUE,
  net_debit_cap NUMERIC,
  sftp_username VARCHAR(255),
  server_certificate_expiry TIMESTAMP
);

CREATE TABLE running_balance (
  master_account_rtn NUMERIC PRIMARY KEY REFERENCES bank_details(master_account_rtn),
  current_running_balance NUMERIC,
  last_updated_at TIMESTAMP
);

CREATE TABLE central_ledger_entries (
  entry_id NUMERIC PRIMARY KEY,
  master_account_rtn NUMERIC REFERENCES bank_details(master_account_rtn),
  activity_source_rtn NUMERIC,
  amount_cents NUMERIC,
  rail_type VARCHAR(255),
  external_ref_id VARCHAR(255),
  effective_date TIMESTAMP
);

CREATE TABLE ach_participants (
  primary_routing_transit_number NUMERIC PRIMARY KEY REFERENCES bank_details(primary_routing_transit_number),
  type VARCHAR(255),
  restricted INT
);
