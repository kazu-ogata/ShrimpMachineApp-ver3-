import sqlite3, os, datetime, bcrypt, uuid
from pymongo import MongoClient
from bson import ObjectId

# Configuration
DB_PATH = "local.db"
MONGO_URI = "mongodb+srv://qajgvalencia:BUxIhYb4nDlfH4DV@cluster0.h07iggq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_DB_NAME = "test"

# Database Initialization
def init_db():
    """Initialize local SQLite database tables."""
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Create Users table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY,
        username TEXT,
        email TEXT,
        password TEXT
    )
    """)
    
    # 2. Create Biomass Records table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS biomass_records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ownerId TEXT,
        recordId TEXT,
        shrimpCount INTEGER,
        biomass REAL,
        feedMeasurement REAL,
        dateTime TEXT,
        synced INTEGER DEFAULT 0,
        dispensed_slots TEXT DEFAULT ''
    )
    """)

    # 3. Create Session table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS session (
        id INTEGER PRIMARY KEY CHECK (id = 1), 
        userId TEXT,
        expiry TEXT
    )
    """)

    # 4. Patch for existing DBs (if the column wasn't there before)
    try:
        conn.execute("ALTER TABLE biomass_records ADD COLUMN dispensed_slots TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    conn.commit()
    conn.close()

def get_active_session():
    """Returns userId if a valid session exists, else None."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT userId, expiry FROM session WHERE id = 1").fetchone()
        conn.close()
        if row:
            uid, expiry_str = row
            expiry = datetime.datetime.fromisoformat(expiry_str)
            if datetime.datetime.now() < expiry:
                return uid
            else:
                clear_session() 
    except Exception as e:
        print(f"Session check error: {e}")
    return None

def save_session(user_id, days=30):
    expiry = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO session (id, userId, expiry) VALUES (1, ?, ?)", (user_id, expiry))
    conn.commit()
    conn.close()

def clear_session():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM session")
    conn.commit()
    conn.close()

def get_cached_username(user_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else "User"

# QR Handshake Functions
def create_qr_session():
    """Generates a unique ID and puts it in MongoDB to wait for a mobile scan."""
    session_id = str(uuid.uuid4())
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB_NAME]
        db["qrsessions"].insert_one({
            "sessionId": session_id,
            "userId": None,
            "status": "pending",
            "createdAt": datetime.datetime.utcnow() 
        })
        return session_id
    except Exception as e:
        print("MongoDB QR Session Error:", e)
        return None
    
def poll_for_login(session_id):
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        db = client[MONGO_DB_NAME]
        session = db["qrsessions"].find_one({"sessionId": session_id})
        
        if session and session.get("userId"):
            user_id = session["userId"]
            # Try to find user by ObjectId or by String
            user_data = db["users"].find_one({"_id": ObjectId(str(user_id))})
            
            if user_data:
                cache_user(str(user_id), user_data['username'], user_data['email'], user_data['password'])
                return str(user_id)
    except Exception as e:
        print(f"Polling error: {e}")
    return None

# Local User Caching
def cache_user(uid, username, email, hashed_pw):
    """Save user locally so they can log in offline next time."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT OR IGNORE INTO users(id, username, email, password)
    VALUES(?,?,?,?)
    """, (uid, username, email, hashed_pw))
    conn.commit()
    conn.close()

# Biomass Record Handling
def save_biomass_record(owner_id, shrimp_count, biomass, feed_measurement):
    conn = sqlite3.connect(DB_PATH)
    record_id = str(uuid.uuid4())
    # Standardize to UTC ISO format string for local storage
    date_time = datetime.datetime.now().isoformat()
    conn.execute("""
    INSERT INTO biomass_records(ownerId, recordId, shrimpCount, biomass, feedMeasurement, dateTime, synced)
    VALUES(?,?,?,?,?, ?,0)
    """, (owner_id, record_id, shrimp_count, biomass, feed_measurement, date_time))
    conn.commit()
    conn.close()

def get_all_records(owner_id):
    """Retrieve all local records belonging to a specific user."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM biomass_records WHERE ownerId=? ORDER BY id DESC",
        (owner_id,)
    ).fetchall()
    conn.close()
    return rows

def get_last_record(owner_id=None):
    conn = sqlite3.connect(DB_PATH)
    if owner_id:
        row = conn.execute(
            "SELECT * FROM biomass_records WHERE ownerId=? ORDER BY id DESC LIMIT 1",
            (owner_id,)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM biomass_records ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row

def delete_record(record_id, owner_id):
    """Delete a specific record locally (and try MongoDB if synced)."""
    conn = sqlite3.connect(DB_PATH)
    record = conn.execute(
        "SELECT recordId, synced FROM biomass_records WHERE id=? AND ownerId=?",
        (record_id, owner_id)
    ).fetchone()

    if not record:
        conn.close()
        return

    record_uuid, synced = record
    conn.execute("DELETE FROM biomass_records WHERE id=? AND ownerId=?", (record_id, owner_id))
    conn.commit()
    conn.close()

    if synced == 1:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
            db = client[MONGO_DB_NAME]
            db["biomassrecords"].delete_one({"recordId": record_uuid})
        except Exception:
            pass

def sync_biomass_records(owner_id):
    """Sync only the current user's unsynced records to MongoDB Atlas."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, ownerId, recordId, shrimpCount, biomass, feedMeasurement, dateTime
        FROM biomass_records
        WHERE synced=0 AND ownerId=?
    """, (owner_id,)).fetchall()

    if not rows:
        conn.close()
        return 0

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
        db = client[MONGO_DB_NAME]          
        col = db["biomassrecords"]            

        docs = []
        local_ids = []
        for (l_id, o_id, r_id, count, bio, feed, dt) in rows:
            # 1. Convert ISO string back to UTC datetime object for MongoDB
            dt_obj = datetime.datetime.fromisoformat(dt).replace(tzinfo=datetime.timezone.utc)
            
            # 2. Robust ownerId formatting
            try:
                formatted_owner_id = ObjectId(str(o_id))
            except:
                formatted_owner_id = str(o_id)

            docs.append({
                "ownerId": formatted_owner_id,
                "recordId": r_id,
                "shrimpCount": count,
                "biomass": bio,
                "feedMeasurement": feed,
                "dateTime": dt_obj,
                "dispensed_slots": "" # Ensure column exists in MongoDB
            })
            local_ids.append(l_id)

        if docs:
            col.insert_many(docs)
            # Update sync status for the specific rows pushed
            for l_id in local_ids:
                conn.execute("UPDATE biomass_records SET synced=1 WHERE id=?", (l_id,))
            conn.commit()
            n = len(docs)
        else:
            n = 0
    except Exception as e:
        print(f"Cloud Sync Error: {e}")
        n = 0

    conn.close()
    return n

def update_dispense_status(sqlite_id, slots_string):
    """Saves which slots (6am, 10am, etc) have been clicked to the local DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE biomass_records SET dispensed_slots = ? WHERE id = ?", (slots_string, sqlite_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating dispense status: {e}")

def verify_user_credentials(identifier, password):
    """Primary check against MongoDB Atlas, falls back to Local for offline support."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB_NAME]
        
        user_data = db["users"].find_one({
            "$or": [{"email": identifier}, {"username": identifier}]
        })

        if user_data:
            hashed_pw = user_data['password']
            pw_bytes = hashed_pw if isinstance(hashed_pw, bytes) else hashed_pw.encode('utf-8')
            
            if bcrypt.checkpw(password.encode('utf-8'), pw_bytes):
                uid = str(user_data['_id'])
                cache_user(uid, user_data['username'], user_data['email'], hashed_pw)
                return uid
    except Exception as e:
        print(f"MongoDB Login Error: {e}")

    # Offline fallback
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, password FROM users WHERE username=? OR email=?", 
        (identifier, identifier)
    ).fetchone()
    conn.close()

    if row:
        user_id, hashed_pw = row
        try:
            pw_bytes = hashed_pw if isinstance(hashed_pw, bytes) else hashed_pw.encode('utf-8')
            if bcrypt.checkpw(password.encode('utf-8'), pw_bytes):
                return user_id
        except Exception:
            pass

    return None
