import sqlite3 # This is the library that lets Python talk to SQL databases

def create_tables():
    """
    This function sets up the entire database from scratch.
    It creates 'Tables' which are like Excel sheets for different types of data.
    """
    try:
        # Step 1: Open a connection to the database file.
        # If the file 'tripmates.db' doesn't exist, it will be created automatically.
        conn = sqlite3.connect('instance/tripmates.db')
        
        # Step 2: Create a 'cursor'.
        # Think of the cursor as a pen that we use to write and run SQL commands.
        cur = conn.cursor()

        # --- 1. User Table ---
        # Stores information about people who register on the website.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique ID for every person (1, 2, 3...)
            name TEXT NOT NULL,                    -- Person's name (required)
            email TEXT NOT NULL UNIQUE,            -- Email (must be unique, no duplicates)
            password_hash TEXT NOT NULL            -- Encrypted password for security
        )
        ''')

        # --- 2. Group Table ---
        # Groups allow multiple friends to plan a trip together and chat.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS "group" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,                    -- Group name (e.g., 'Summer Squad')
            description TEXT,                      -- Optional description
            admin_id INTEGER NOT NULL,             -- The ID of the user who created the group
            join_token TEXT UNIQUE,                -- A secret code for the invite link
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,           -- 1 means active, 0 means deleted
            approval_required BOOLEAN DEFAULT 0,   -- New: admin must approve
            FOREIGN KEY (admin_id) REFERENCES user(id) -- Link this to the 'user' table
        )
        ''')

        # --- 3. Group Members ---
        # A list showing which users belong to which groups (Many-to-Many).
        cur.execute('''
        CREATE TABLE IF NOT EXISTS group_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,             -- ID of the group
            user_id INTEGER NOT NULL,              -- ID of the user
            role TEXT NOT NULL DEFAULT 'member',   -- Can be 'admin' or 'member'
            status TEXT NOT NULL DEFAULT 'active', -- New: 'active' or 'pending'
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES "group"(id),
            FOREIGN KEY (user_id) REFERENCES user(id),
            UNIQUE(group_id, user_id)              -- Prevents a user from joining the same group twice
        )
        ''')

        # --- 4. Group Messages ---
        # Stores the chat history for our real-time group chat.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS group_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,                 -- The actual chat text
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            media_filename TEXT,                   -- Optional: filename if they upload an image
            location_lat REAL,                     -- GPS latitude if they share location
            location_lng REAL,                     -- GPS longitude
            location_label TEXT,
            FOREIGN KEY (group_id) REFERENCES "group"(id),
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
        ''')

        # --- 5. Trip Table ---
        # The main information about where and when the trip is happening.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS trip (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,              -- The owner who created this trip
            group_id INTEGER,                      -- Optional: links the trip to a group
            title TEXT NOT NULL,                   -- e.g., 'Goa Trip'
            destination TEXT NOT NULL,             -- e.g., 'Panjim'
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            description TEXT,
            cover_image TEXT,                      -- Path to the trip's background image
            share_token TEXT UNIQUE,               -- Unique token for sharing this trip
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (group_id) REFERENCES "group"(id)
        )
        ''')

        # --- 6. Itinerary Items ---
        # The daily plan or activities for each trip.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS itinerary_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,              -- Which trip does this belong to?
            title TEXT NOT NULL,                   -- e.g., 'Dinner at Beach'
            description TEXT,
            datetime TIMESTAMP NOT NULL,           -- When is this activity?
            location TEXT,
            cost NUMERIC(10,2),                    -- Estimated cost
            tags TEXT,
            FOREIGN KEY (trip_id) REFERENCES trip(id)
        )
        ''')
        
        # --- 7. Expenses Table ---
        # Tracks money spent during the trip.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS expense (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,             -- Which trip did we spend this on?
            title TEXT NOT NULL,                  -- e.g., 'Dinner at Beach'
            amount NUMERIC(12,2) NOT NULL,        -- Total cost
            payer_id INTEGER NOT NULL,             -- Who paid the bill?
            notes TEXT,                           -- Extra details
            FOREIGN KEY (trip_id) REFERENCES trip(id),
            FOREIGN KEY (payer_id) REFERENCES user(id)
        )
        ''')

        # --- 8. Expense Participants Table ---
        # Shows who shared the cost of a specific expense.
        cur.execute('''
        CREATE TABLE IF NOT EXISTS expense_participants (
            expense_id INTEGER NOT NULL,          -- The ID of the expense
            user_id INTEGER NOT NULL,             -- The ID of the participant
            PRIMARY KEY (expense_id, user_id),
            FOREIGN KEY (expense_id) REFERENCES expense(id),
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
        ''')

        # --- Performance Boosters (Indexes) ---
        # Indexes make searching the database much faster.
        cur.execute('CREATE INDEX IF NOT EXISTS ix_group_join_token ON "group" (join_token)')
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_group_member ON group_member (group_id, user_id)')

        # Final Step: Commit (Save) the changes.
        # SQL won't save your work unless you explicitly tell it to 'Commit'.
        conn.commit()
        print("Successfully created database tables for TripMates")

    except Exception as e:
        # If anything goes wrong, we 'Rollback' (Undo) to prevent mistakes.
        print(f"An error occurred: {str(e)}")
        conn.rollback()
    finally:
        # Always close the connection when done to free up memory.
        conn.close()

# This part tells Python to run the function when you start the script.
if __name__ == '__main__':
    create_tables()
