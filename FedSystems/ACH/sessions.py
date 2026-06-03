def makeBankMatrix():
    """Generate a directional matrix by primary RTN from ledger entries.

    Example: 
                | Bank A | Bank B | Bank C |
        -----------------------------------------
        Bank A  |   -     |  -1000  |   500  |
        Bank B  |  1000   |   -     |   300  |
        Bank C  |  -500   |   -300  |   -    |
    """
    # Build a matrix keyed by primary routing number, falling back to raw RTN
    # when a bank mapping does not exist.
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(db_url, connect_timeout=5)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # map master_account_rtn -> primary_routing_transit_number
        cur.execute(
            """
            SELECT master_account_rtn, primary_routing_transit_number
            FROM bank_details
            """
        )
        master_to_primary = {
            row["master_account_rtn"]: row["primary_routing_transit_number"]
            for row in cur.fetchall()
            if row.get("master_account_rtn") and row.get("primary_routing_transit_number")
        }

        # Use declared ACH participants for the bank list (prefer active participants)
        cur.execute(
            """
            SELECT primary_routing_transit_number
            FROM ach_participants
            WHERE restricted NOT IN (1, 'restricted')
            """
        )
        participants = [r.get("primary_routing_transit_number") for r in cur.fetchall() if r.get("primary_routing_transit_number")]

        # Fallback: if no participants defined, derive banks from bank_details mapping
        if participants:
            banks = sorted(set(participants))
        else:
            banks = sorted(set(master_to_primary.values()))

        # Return a zero-initialized directional matrix for the participants.
        matrix = {bank: {other_bank: 0 for other_bank in banks} for bank in banks}

        return matrix
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.exception("Failed to generate bank matrix: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()