"""
Database migration script for admin and subscription features
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from modules.database import db_manager
from modules.config.settings import settings

def migrate_database():
    """Run database migrations for admin and subscription features"""
    conn = db_manager.get_connection()
    cur = conn.cursor()
    
    try:
        print("Starting database migration...")
        
        # Check if we're using MySQL or SQLite
        use_rds = settings.USE_RDS
        
        # 1. Create admin_users table
        print("Creating admin_users table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    is_super_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP NULL,
                    INDEX idx_email (email),
                    INDEX idx_super_admin (is_super_admin)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_super_admin BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_email ON admin_users (email)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_super_admin ON admin_users (is_super_admin)")
        
        # 2. Create subscription_plans table
        print("Creating subscription_plans table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    description TEXT,
                    price_monthly DECIMAL(10,2) DEFAULT 0.00,
                    price_annual DECIMAL(10,2) DEFAULT 0.00,
                    storage_gb INT DEFAULT 0,
                    project_limit INT DEFAULT 0,
                    user_limit INT DEFAULT 1,
                    action_limit INT DEFAULT 0,
                    features JSON,
                    is_active BOOLEAN DEFAULT TRUE,
                    has_free_trial BOOLEAN DEFAULT FALSE,
                    trial_days INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_name (name),
                    INDEX idx_is_active (is_active)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    price_monthly REAL DEFAULT 0.00,
                    price_annual REAL DEFAULT 0.00,
                    storage_gb INTEGER DEFAULT 0,
                    project_limit INTEGER DEFAULT 0,
                    user_limit INTEGER DEFAULT 1,
                    action_limit INTEGER DEFAULT 0,
                    features TEXT,  -- Store as JSON string
                    is_active BOOLEAN DEFAULT 1,
                    has_free_trial BOOLEAN DEFAULT 0,
                    trial_days INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_name ON subscription_plans (name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_active ON subscription_plans (is_active)")
        
        # 3. Create user_subscriptions table
        print("Creating user_subscriptions table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    plan_id INT NOT NULL,
                    stripe_subscription_id VARCHAR(255),
                    stripe_customer_id VARCHAR(255),
                    current_period_start TIMESTAMP,
                    current_period_end TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'active',
                    interval VARCHAR(20) DEFAULT 'monthly',
                    auto_renew BOOLEAN DEFAULT TRUE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    FOREIGN KEY (plan_id) REFERENCES subscription_plans (id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_plan_id (plan_id),
                    INDEX idx_stripe_subscription (stripe_subscription_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_id INTEGER NOT NULL,
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    current_period_start DATETIME,
                    current_period_end DATETIME,
                    status TEXT DEFAULT 'active',
                    interval TEXT DEFAULT 'monthly',
                    auto_renew BOOLEAN DEFAULT 1,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    FOREIGN KEY (plan_id) REFERENCES subscription_plans (id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sub_user_id ON user_subscriptions (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sub_plan_id ON user_subscriptions (plan_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sub_status ON user_subscriptions (status)")
        
        # 4. Create user_storage table
        print("Creating user_storage table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_storage (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT UNIQUE NOT NULL,
                    used_storage_mb INT DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_storage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    used_storage_mb INTEGER DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_storage_user_id ON user_storage (user_id)")
        
        # 5. Create feedback table
        print("Creating feedback table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    ai_response TEXT NOT NULL,
                    rating ENUM('positive', 'negative') NOT NULL,
                    project_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id),
                    INDEX idx_rating (rating),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    ai_response TEXT NOT NULL,
                    rating TEXT CHECK(rating IN ('positive', 'negative')) NOT NULL,
                    project_name TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback (rating)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at)")
        
        # 6. Create ai_models table
        print("Creating ai_models table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_models (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    provider VARCHAR(100) NOT NULL,
                    model_name VARCHAR(255) NOT NULL,
                    is_active BOOLEAN DEFAULT FALSE,
                    config JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_provider (provider),
                    INDEX idx_is_active (is_active)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 0,
                    config TEXT,  -- Store as JSON string
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_provider ON ai_models (provider)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_active ON ai_models (is_active)")
        
        # 7. Create recently_viewed_projects table
        print("Creating recently_viewed_projects table...")
        if use_rds:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recently_viewed_projects (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    project_id VARCHAR(255) NOT NULL,
                    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    view_count INT DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    UNIQUE KEY unique_user_project (user_id, project_id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_viewed_at (viewed_at)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recently_viewed_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    viewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    view_count INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    UNIQUE (user_id, project_id)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recent_user_id ON recently_viewed_projects (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recent_viewed_at ON recently_viewed_projects (viewed_at)")
        
        # 8. Add is_active column to userdata table if it doesn't exist
        print("Checking userdata table for is_active column...")
        if use_rds:
            cur.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'userdata' 
                AND COLUMN_NAME = 'is_active'
            """, (settings.DB_NAME,))
            column_exists = cur.fetchone()[0] > 0
            
            if not column_exists:
                print("Adding is_active column to userdata table...")
                cur.execute("ALTER TABLE userdata ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
                cur.execute("CREATE INDEX idx_user_active ON userdata (is_active)")
        else:
            cur.execute("PRAGMA table_info(userdata)")
            columns = [row[1] for row in cur.fetchall()]
            
            if 'is_active' not in columns:
                print("Adding is_active column to userdata table...")
                cur.execute("ALTER TABLE userdata ADD COLUMN is_active BOOLEAN DEFAULT 1")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_user_active ON userdata (is_active)")
        
        # 9. Add profile_image column to userdata table if it doesn't exist
        print("Checking userdata table for profile_image column...")
        if use_rds:
            cur.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'userdata' 
                AND COLUMN_NAME = 'profile_image'
            """, (settings.DB_NAME,))
            column_exists = cur.fetchone()[0] > 0
            
            if not column_exists:
                print("Adding profile_image column to userdata table...")
                cur.execute("ALTER TABLE userdata ADD COLUMN profile_image TEXT")
        else:
            cur.execute("PRAGMA table_info(userdata)")
            columns = [row[1] for row in cur.fetchall()]
            
            if 'profile_image' not in columns:
                print("Adding profile_image column to userdata table...")
                cur.execute("ALTER TABLE userdata ADD COLUMN profile_image TEXT")
        
        # 10. Create default admin user if no admin exists
        print("Creating default admin user...")
        cur.execute("SELECT COUNT(*) FROM admin_users")
        admin_count = cur.fetchone()[0]
        
        if admin_count == 0:
            import hashlib
            default_password = hashlib.sha256("admin123".encode()).hexdigest()
            cur.execute(
                "INSERT INTO admin_users (username, email, password, is_super_admin) VALUES (%s, %s, %s, %s)" if use_rds else 
                "INSERT INTO admin_users (username, email, password, is_super_admin) VALUES (?, ?, ?, ?)",
                ("admin", "admin@esticore.com", default_password, True)
            )
            print("✅ Default admin user created: admin@esticore.com / admin123")
        
        # 11. Insert default AI models
        print("Creating default AI models...")
        default_models = [
            {
                "name": "GPT-4",
                "provider": "OpenAI",
                "model_name": "gpt-4",
                "is_active": True,
                "config": '{"temperature": 0.7, "max_tokens": 2000}'
            },
            {
                "name": "GPT-3.5-Turbo",
                "provider": "OpenAI", 
                "model_name": "gpt-3.5-turbo",
                "is_active": False,
                "config": '{"temperature": 0.7, "max_tokens": 2000}'
            },
            {
                "name": "Claude-2",
                "provider": "Anthropic",
                "model_name": "claude-2",
                "is_active": False,
                "config": '{"temperature": 0.7, "max_tokens": 2000}'
            }
        ]
        
        for model in default_models:
            cur.execute(
                "INSERT OR IGNORE INTO ai_models (name, provider, model_name, is_active, config) VALUES (%s, %s, %s, %s, %s)" if use_rds else 
                "INSERT OR IGNORE INTO ai_models (name, provider, model_name, is_active, config) VALUES (?, ?, ?, ?, ?)",
                (model["name"], model["provider"], model["model_name"], model["is_active"], model["config"])
            )
        
        conn.commit()
        print("✅ Database migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {str(e)}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()