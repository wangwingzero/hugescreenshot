//! 历史记录数据库
//!
//! 使用 SQLite 存储截图历史记录
//!
//! 性能优化:
//! - WAL 模式: 支持并发读写
//! - 连接池: 复用数据库连接，避免频繁创建/销毁
//! - 事务支持: 批量操作使用事务，提升性能
//! - PRAGMA 优化: 内存缓存、同步模式等
//! - 查询性能监控: 记录查询耗时，超过阈值记录警告
//!
//! **Validates: Requirements 3.7, 4.3, 4.4, 4.6**

use r2d2::{Pool, PooledConnection};
use r2d2_sqlite::SqliteConnectionManager;
use rusqlite::params;
use serde::{Deserialize, Serialize};
use std::time::Instant;
use tracing::{debug, info, warn};

use crate::error::HuGeResult;

/// 连接池类型别名
type DbPool = Pool<SqliteConnectionManager>;
type DbConn = PooledConnection<SqliteConnectionManager>;

/// 连接池配置
///
/// 历史库不是高并发场景：UI 串行调用 + 后台 OCR 缓存写入，1-2 个连接足够。
/// 减小 POOL_SIZE 直接降低 page cache 总占用（每连接 cache_size 独立）。
const POOL_SIZE: u32 = 2;
const POOL_MIN_IDLE: u32 = 0;

/// 截图历史记录
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScreenshotRecord {
    /// 记录 ID
    pub id: i64,
    /// 创建时间（ISO 8601 格式）
    pub created_at: String,
    /// 文件路径
    pub file_path: String,
    /// 缩略图路径
    pub thumbnail_path: Option<String>,
    /// 图像宽度
    pub width: u32,
    /// 图像高度
    pub height: u32,
    /// 文件大小（字节）
    pub file_size: Option<i64>,
    /// OCR 识别文本
    pub ocr_text: Option<String>,
    /// 标签（JSON 数组）
    pub tags: Option<String>,
    /// 元数据（JSON 对象）
    pub metadata: Option<String>,
    /// 图片哈希（用于去重）
    pub image_hash: Option<String>,
    /// 是否置顶
    pub is_pinned: bool,
    /// OCR 缓存时间戳
    pub ocr_cached_at: Option<String>,
    /// 内容类型：image 或 text
    pub content_type: String,
    /// 文字内容（仅文字类型有值）
    pub text_content: Option<String>,
}

impl Default for ScreenshotRecord {
    fn default() -> Self {
        Self {
            id: 0,
            created_at: String::new(),
            file_path: String::new(),
            thumbnail_path: None,
            width: 0,
            height: 0,
            file_size: None,
            ocr_text: None,
            tags: None,
            metadata: None,
            image_hash: None,
            is_pinned: false,
            ocr_cached_at: None,
            content_type: "image".to_string(),
            text_content: None,
        }
    }
}

/// 历史记录数据库管理器
///
/// 使用 r2d2 连接池管理 SQLite 连接，支持并发访问。
pub struct HistoryDatabase {
    pool: DbPool,
}

impl HistoryDatabase {
    /// 转义 SQL LIKE 模式中的通配符字符（%, _, \）
    ///
    /// 防止用户输入中的 `%` 和 `_` 被解释为 SQL 通配符。
    /// 配合 `ESCAPE '\'` 子句使用。
    fn escape_like_pattern(input: &str) -> String {
        input.replace('\\', "\\\\").replace('%', "\\%").replace('_', "\\_")
    }

    /// 打开或创建数据库
    ///
    /// # 参数
    ///
    /// - `db_path`: 数据库文件路径
    ///
    /// # 性能优化
    ///
    /// - WAL 模式: 支持并发读写
    /// - 连接池: 最多 2 个连接，按需创建
    /// - PRAGMA 优化: 8MB/连接 cache、64MB mmap、NORMAL 同步模式
    pub fn open(db_path: &str) -> HuGeResult<Self> {
        info!("初始化数据库连接池: {}", db_path);

        // 创建连接管理器，设置初始化回调
        let manager = SqliteConnectionManager::file(db_path).with_init(|conn| {
            // 启用 WAL 模式 - 支持并发读写
            // cache_size = -8000 (8MB / 连接, 池 2 连接共 16MB), mmap_size = 64MB
            // 截图历史库典型规模 < 100MB, 64MB mmap 已能容纳热数据
            conn.execute_batch(
                r#"
                    PRAGMA journal_mode = WAL;
                    PRAGMA synchronous = NORMAL;
                    PRAGMA cache_size = -8000;
                    PRAGMA temp_store = MEMORY;
                    PRAGMA mmap_size = 67108864;
                    PRAGMA busy_timeout = 5000;
                "#,
            )?;
            Ok(())
        });

        // 创建连接池
        let pool = Pool::builder()
            .max_size(POOL_SIZE)
            .min_idle(Some(POOL_MIN_IDLE))
            .build(manager)
            .map_err(|e| crate::error::HuGeError::Database(format!("创建连接池失败: {}", e)))?;

        let db = Self { pool };
        db.init_schema()?;

        info!("数据库连接池初始化成功，最大连接数: {}", POOL_SIZE);
        Ok(db)
    }

    /// 获取数据库连接
    fn get_conn(&self) -> HuGeResult<DbConn> {
        self.pool
            .get()
            .map_err(|e| crate::error::HuGeError::Database(format!("获取数据库连接失败: {}", e)))
    }

    /// 初始化数据库 schema
    fn init_schema(&self) -> HuGeResult<()> {
        let conn = self.get_conn()?;
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT NOT NULL,
                thumbnail_path TEXT,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                file_size INTEGER,
                ocr_text TEXT,
                tags TEXT,
                metadata TEXT,
                image_hash TEXT,
                is_pinned INTEGER DEFAULT 0,
                ocr_cached_at DATETIME
            );

            CREATE INDEX IF NOT EXISTS idx_screenshots_created_at
                ON screenshots(created_at);

            CREATE INDEX IF NOT EXISTS idx_screenshots_image_hash
                ON screenshots(image_hash);

            CREATE INDEX IF NOT EXISTS idx_screenshots_is_pinned
                ON screenshots(is_pinned);
            "#,
        )?;

        // 检查并添加新列（数据库迁移）
        self.migrate_schema(&conn)?;

        Ok(())
    }

    /// 数据库 Schema 迁移
    fn migrate_schema(&self, conn: &DbConn) -> HuGeResult<()> {
        // 获取现有列
        let mut stmt = conn.prepare("PRAGMA table_info(screenshots)")?;
        let columns: Vec<String> =
            stmt.query_map([], |row| row.get::<_, String>(1))?.filter_map(|r| r.ok()).collect();

        // 添加缺失的列
        let migrations = [
            ("image_hash", "ALTER TABLE screenshots ADD COLUMN image_hash TEXT"),
            ("is_pinned", "ALTER TABLE screenshots ADD COLUMN is_pinned INTEGER DEFAULT 0"),
            ("ocr_cached_at", "ALTER TABLE screenshots ADD COLUMN ocr_cached_at DATETIME"),
            (
                "content_type",
                "ALTER TABLE screenshots ADD COLUMN content_type TEXT NOT NULL DEFAULT 'image'",
            ),
            ("text_content", "ALTER TABLE screenshots ADD COLUMN text_content TEXT"),
        ];

        for (column, sql) in migrations {
            if !columns.contains(&column.to_string()) {
                info!("迁移数据库: 添加列 {}", column);
                conn.execute(sql, [])?;
            }
        }

        Ok(())
    }

    /// 添加截图记录
    ///
    /// # 参数
    ///
    /// - `record`: 截图记录（id 字段会被忽略）
    ///
    /// # 返回
    ///
    /// 返回新记录的 ID
    pub fn insert(&self, record: &ScreenshotRecord) -> HuGeResult<i64> {
        let conn = self.get_conn()?;
        conn.execute(
            r#"
            INSERT INTO screenshots
                (file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, content_type, text_content)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)
            "#,
            params![
                record.file_path,
                record.thumbnail_path,
                record.width,
                record.height,
                record.file_size,
                record.ocr_text,
                record.tags,
                record.metadata,
                record.image_hash,
                record.is_pinned as i32,
                record.content_type,
                record.text_content,
            ],
        )?;
        Ok(conn.last_insert_rowid())
    }

    /// 检查图片哈希是否已存在
    ///
    /// # 参数
    ///
    /// - `hash`: 图片 MD5 哈希
    ///
    /// # 返回
    ///
    /// 如果存在返回记录 ID，否则返回 None
    pub fn find_by_hash(&self, hash: &str) -> HuGeResult<Option<i64>> {
        let conn = self.get_conn()?;
        let result: Result<i64, _> = conn.query_row(
            "SELECT id FROM screenshots WHERE image_hash = ?1 LIMIT 1",
            params![hash],
            |row| row.get(0),
        );

        match result {
            Ok(id) => Ok(Some(id)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(crate::error::HuGeError::Database(format!("查询哈希失败: {}", e))),
        }
    }

    /// 获取截图记录
    ///
    /// # 参数
    ///
    /// - `id`: 记录 ID
    pub fn get(&self, id: i64) -> HuGeResult<Option<ScreenshotRecord>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, created_at, file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, ocr_cached_at, content_type, text_content FROM screenshots WHERE id = ?1",
        )?;

        let mut rows = stmt.query(params![id])?;

        if let Some(row) = rows.next()? {
            Ok(Some(Self::row_to_record(row)?))
        } else {
            Ok(None)
        }
    }

    /// 从数据库行转换为记录
    fn row_to_record(row: &rusqlite::Row) -> rusqlite::Result<ScreenshotRecord> {
        let is_pinned: i32 = row.get(11)?;
        Ok(ScreenshotRecord {
            id: row.get(0)?,
            created_at: row.get(1)?,
            file_path: row.get(2)?,
            thumbnail_path: row.get(3)?,
            width: row.get(4)?,
            height: row.get(5)?,
            file_size: row.get(6)?,
            ocr_text: row.get(7)?,
            tags: row.get(8)?,
            metadata: row.get(9)?,
            image_hash: row.get(10)?,
            is_pinned: is_pinned != 0,
            ocr_cached_at: row.get(12)?,
            content_type: row.get::<_, Option<String>>(13)?.unwrap_or_else(|| "image".to_string()),
            text_content: row.get(14)?,
        })
    }

    /// 删除截图记录
    ///
    /// # 参数
    ///
    /// - `id`: 记录 ID
    pub fn delete(&self, id: i64) -> HuGeResult<bool> {
        let conn = self.get_conn()?;
        let affected = conn.execute("DELETE FROM screenshots WHERE id = ?1", params![id])?;
        Ok(affected > 0)
    }

    /// 搜索截图记录
    ///
    /// # 参数
    ///
    /// - `query`: 搜索关键词（搜索 OCR 文本和标签）
    /// - `limit`: 最大返回数量
    /// - `offset`: 偏移量
    pub fn search(
        &self,
        query: &str,
        limit: u32,
        offset: u32,
    ) -> HuGeResult<Vec<ScreenshotRecord>> {
        let conn = self.get_conn()?;
        let search_pattern = format!("%{}%", Self::escape_like_pattern(query));
        let mut stmt = conn.prepare(
            r#"
            SELECT id, created_at, file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, ocr_cached_at, content_type, text_content
            FROM screenshots
            WHERE ocr_text LIKE ?1 ESCAPE '\' OR tags LIKE ?1 ESCAPE '\'
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT ?2 OFFSET ?3
            "#,
        )?;

        let rows = stmt.query_map(params![search_pattern, limit, offset], Self::row_to_record)?;

        let mut records = Vec::new();
        for row in rows {
            records.push(row?);
        }
        Ok(records)
    }

    /// 获取最近的截图记录
    ///
    /// # 参数
    ///
    /// - `limit`: 最大返回数量
    pub fn get_recent(&self, limit: u32) -> HuGeResult<Vec<ScreenshotRecord>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, created_at, file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, ocr_cached_at, content_type, text_content FROM screenshots ORDER BY is_pinned DESC, created_at DESC LIMIT ?1",
        )?;

        let rows = stmt.query_map(params![limit], Self::row_to_record)?;

        let mut records = Vec::new();
        for row in rows {
            records.push(row?);
        }
        Ok(records)
    }

    /// 获取记录总数
    pub fn count(&self) -> HuGeResult<i64> {
        let conn = self.get_conn()?;
        let count: i64 =
            conn.query_row("SELECT COUNT(*) FROM screenshots", [], |row| row.get(0))?;
        Ok(count)
    }

    /// 更新截图记录
    ///
    /// # 参数
    ///
    /// - `id`: 记录 ID
    /// - `updates`: 更新内容
    pub fn update(&self, id: i64, updates: &ScreenshotRecordUpdate) -> HuGeResult<bool> {
        let conn = self.get_conn()?;
        let mut set_clauses = Vec::new();
        let mut params_vec: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();

        if let Some(ref ocr_text) = updates.ocr_text {
            set_clauses.push("ocr_text = ?");
            params_vec.push(Box::new(ocr_text.clone()));
        }
        if let Some(ref tags) = updates.tags {
            set_clauses.push("tags = ?");
            params_vec.push(Box::new(tags.clone()));
        }
        if let Some(ref metadata) = updates.metadata {
            set_clauses.push("metadata = ?");
            params_vec.push(Box::new(metadata.clone()));
        }
        if let Some(ref thumbnail_path) = updates.thumbnail_path {
            set_clauses.push("thumbnail_path = ?");
            params_vec.push(Box::new(thumbnail_path.clone()));
        }
        if let Some(is_pinned) = updates.is_pinned {
            set_clauses.push("is_pinned = ?");
            params_vec.push(Box::new(is_pinned as i32));
        }
        if let Some(ref ocr_cached_at) = updates.ocr_cached_at {
            set_clauses.push("ocr_cached_at = ?");
            params_vec.push(Box::new(ocr_cached_at.clone()));
        }

        if set_clauses.is_empty() {
            return Ok(false);
        }

        params_vec.push(Box::new(id));

        let sql = format!("UPDATE screenshots SET {} WHERE id = ?", set_clauses.join(", "));

        debug!("更新历史记录 {}: {}", id, sql);

        let params_refs: Vec<&dyn rusqlite::ToSql> =
            params_vec.iter().map(|p| p.as_ref()).collect();
        let affected = conn.execute(&sql, params_refs.as_slice())?;

        Ok(affected > 0)
    }

    /// 批量删除截图记录（使用事务）
    ///
    /// # 参数
    ///
    /// - `ids`: 记录 ID 列表
    pub fn delete_batch(&self, ids: &[i64]) -> HuGeResult<usize> {
        if ids.is_empty() {
            return Ok(0);
        }

        let mut conn = self.get_conn()?;

        // 使用事务进行批量删除
        let tx = conn.transaction()?;

        let placeholders: Vec<String> = ids.iter().map(|_| "?".to_string()).collect();
        let sql = format!("DELETE FROM screenshots WHERE id IN ({})", placeholders.join(", "));

        let params: Vec<&dyn rusqlite::ToSql> =
            ids.iter().map(|id| id as &dyn rusqlite::ToSql).collect();
        let affected = tx.execute(&sql, params.as_slice())?;

        tx.commit()?;

        info!("批量删除 {} 条历史记录", affected);
        Ok(affected)
    }

    /// 批量插入截图记录（使用事务）
    ///
    /// # 参数
    ///
    /// - `records`: 截图记录列表
    ///
    /// # 返回
    ///
    /// 返回插入的记录 ID 列表
    pub fn insert_batch(&self, records: &[ScreenshotRecord]) -> HuGeResult<Vec<i64>> {
        if records.is_empty() {
            return Ok(Vec::new());
        }

        let mut conn = self.get_conn()?;
        let tx = conn.transaction()?;

        let mut ids = Vec::with_capacity(records.len());

        {
            let mut stmt = tx.prepare(
                r#"
                INSERT INTO screenshots
                    (file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, content_type, text_content)
                VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)
                "#,
            )?;

            for record in records {
                stmt.execute(params![
                    record.file_path,
                    record.thumbnail_path,
                    record.width,
                    record.height,
                    record.file_size,
                    record.ocr_text,
                    record.tags,
                    record.metadata,
                    record.image_hash,
                    record.is_pinned as i32,
                    record.content_type,
                    record.text_content,
                ])?;
                ids.push(tx.last_insert_rowid());
            }
        }

        tx.commit()?;

        info!("批量插入 {} 条历史记录", ids.len());
        Ok(ids)
    }

    /// 获取统计信息
    pub fn get_stats(&self) -> HuGeResult<HistoryStats> {
        let conn = self.get_conn()?;

        let total_count: i64 =
            conn.query_row("SELECT COUNT(*) FROM screenshots", [], |row| row.get(0))?;

        let total_size: i64 =
            conn.query_row("SELECT COALESCE(SUM(file_size), 0) FROM screenshots", [], |row| {
                row.get(0)
            })?;

        let today_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM screenshots WHERE date(created_at) = date('now')",
            [],
            |row| row.get(0),
        )?;

        let week_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM screenshots WHERE created_at >= datetime('now', '-7 days')",
            [],
            |row| row.get(0),
        )?;

        let month_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM screenshots WHERE created_at >= datetime('now', '-30 days')",
            [],
            |row| row.get(0),
        )?;

        let pinned_count: i64 =
            conn.query_row("SELECT COUNT(*) FROM screenshots WHERE is_pinned = 1", [], |row| {
                row.get(0)
            })?;

        let uncached_ocr_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM screenshots WHERE ocr_text IS NULL OR ocr_text = ''",
            [],
            |row| row.get(0),
        )?;

        Ok(HistoryStats {
            total_count,
            total_size,
            today_count,
            week_count,
            month_count,
            pinned_count,
            uncached_ocr_count,
        })
    }

    /// 获取未缓存 OCR 的记录
    ///
    /// # 参数
    ///
    /// - `limit`: 最大返回数量
    ///
    /// # 返回
    ///
    /// 返回未缓存 OCR 的记录列表（用于后台 OCR 缓存）
    pub fn get_uncached_ocr_records(&self, limit: u32) -> HuGeResult<Vec<ScreenshotRecord>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare(
            r#"
            SELECT id, created_at, file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, ocr_cached_at, content_type, text_content
            FROM screenshots
            WHERE (ocr_text IS NULL OR ocr_text = '') AND file_path IS NOT NULL AND (content_type IS NULL OR content_type = 'image')
            ORDER BY created_at DESC
            LIMIT ?1
            "#,
        )?;

        let rows = stmt.query_map(params![limit], Self::row_to_record)?;

        let mut records = Vec::new();
        for row in rows {
            records.push(row?);
        }
        Ok(records)
    }

    /// 更新 OCR 缓存
    ///
    /// # 参数
    ///
    /// - `id`: 记录 ID
    /// - `ocr_text`: OCR 识别文本
    pub fn update_ocr_cache(&self, id: i64, ocr_text: &str) -> HuGeResult<bool> {
        let conn = self.get_conn()?;
        let affected = conn.execute(
            "UPDATE screenshots SET ocr_text = ?1, ocr_cached_at = datetime('now') WHERE id = ?2",
            params![ocr_text, id],
        )?;
        Ok(affected > 0)
    }

    /// 切换置顶状态
    ///
    /// # 参数
    ///
    /// - `id`: 记录 ID
    pub fn toggle_pin(&self, id: i64) -> HuGeResult<bool> {
        let conn = self.get_conn()?;
        let affected = conn.execute(
            "UPDATE screenshots SET is_pinned = NOT is_pinned WHERE id = ?1",
            params![id],
        )?;
        Ok(affected > 0)
    }

    /// 清除所有未钉住的记录
    ///
    /// 钉住的记录不会被删除。
    ///
    /// # 返回
    ///
    /// 返回被删除的记录数
    pub fn clear_unpinned(&self) -> HuGeResult<usize> {
        let conn = self.get_conn()?;

        // 先获取要删除的文件路径（用于后续清理文件）
        let mut stmt =
            conn.prepare("SELECT file_path, thumbnail_path FROM screenshots WHERE is_pinned = 0")?;
        let paths: Vec<(String, Option<String>)> = stmt
            .query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, Option<String>>(1)?)))?
            .filter_map(|r| r.ok())
            .collect();

        // 删除记录
        let affected = conn.execute("DELETE FROM screenshots WHERE is_pinned = 0", [])?;

        // 清理关联文件
        for (file_path, thumb_path) in &paths {
            if !file_path.is_empty() {
                let _ = std::fs::remove_file(file_path);
            }
            if let Some(thumb) = thumb_path {
                let _ = std::fs::remove_file(thumb);
            }
        }

        info!("清除了 {} 条未钉住的记录", affected);
        Ok(affected)
    }

    /// 高级搜索截图记录
    ///
    /// # 参数
    ///
    /// - `params`: 搜索参数
    pub fn search_advanced(&self, params: &SearchParams) -> HuGeResult<SearchResult> {
        let conn = self.get_conn()?;
        let mut conditions = Vec::new();
        let mut sql_params: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();

        // 关键词搜索
        if let Some(ref query) = params.query {
            if !query.is_empty() {
                conditions.push("(ocr_text LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')");
                let pattern = format!("%{}%", Self::escape_like_pattern(query));
                sql_params.push(Box::new(pattern.clone()));
                sql_params.push(Box::new(pattern));
            }
        }

        // 日期范围
        if let Some(ref start_date) = params.start_date {
            conditions.push("created_at >= ?");
            sql_params.push(Box::new(start_date.clone()));
        }
        if let Some(ref end_date) = params.end_date {
            conditions.push("created_at <= ?");
            sql_params.push(Box::new(end_date.clone()));
        }

        // 标签过滤
        if let Some(ref tags) = params.tags {
            if !tags.is_empty() {
                for tag in tags {
                    conditions.push("tags LIKE ? ESCAPE '\\'");
                    sql_params.push(Box::new(format!("%\"{}\"", Self::escape_like_pattern(tag))));
                }
            }
        }

        // 仅置顶
        if params.pinned_only.unwrap_or(false) {
            conditions.push("is_pinned = 1");
        }

        let where_clause = if conditions.is_empty() {
            String::new()
        } else {
            format!("WHERE {}", conditions.join(" AND "))
        };

        // 排序
        let order_by = match params.sort_by.as_deref() {
            Some("fileSize") => "file_size",
            _ => "created_at",
        };
        let order_dir = match params.sort_order.as_deref() {
            Some("asc") => "ASC",
            _ => "DESC",
        };

        // 获取总数
        let count_sql = format!("SELECT COUNT(*) FROM screenshots {}", where_clause);
        let count_params: Vec<&dyn rusqlite::ToSql> =
            sql_params.iter().map(|p| p.as_ref()).collect();
        let total: i64 = conn.query_row(&count_sql, count_params.as_slice(), |row| row.get(0))?;

        // 分页
        let limit = params.limit.unwrap_or(50);
        let offset = params.offset.unwrap_or(0);

        sql_params.push(Box::new(limit as i64));
        sql_params.push(Box::new(offset as i64));

        let sql = format!(
            "SELECT id, created_at, file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, ocr_cached_at, content_type, text_content FROM screenshots {} ORDER BY is_pinned DESC, {} {} LIMIT ? OFFSET ?",
            where_clause, order_by, order_dir
        );

        let params_refs: Vec<&dyn rusqlite::ToSql> =
            sql_params.iter().map(|p| p.as_ref()).collect();
        let mut stmt = conn.prepare(&sql)?;
        let rows = stmt.query_map(params_refs.as_slice(), Self::row_to_record)?;

        let mut items = Vec::new();
        for row in rows {
            items.push(row?);
        }

        let has_more = (offset + limit) < total as u32;

        Ok(SearchResult { items, total, has_more })
    }

    /// 执行数据库维护（清理 WAL 文件）
    pub fn vacuum(&self) -> HuGeResult<()> {
        let conn = self.get_conn()?;
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)", [])?;
        info!("数据库 WAL checkpoint 完成");
        Ok(())
    }

    /// 获取连接池状态
    pub fn pool_status(&self) -> PoolStatus {
        let state = self.pool.state();
        PoolStatus {
            connections: state.connections,
            idle_connections: state.idle_connections,
            max_size: POOL_SIZE,
        }
    }

    /// 执行带性能监控的查询
    ///
    /// **Validates: Requirements 4.3, 4.6**
    ///
    /// # 参数
    ///
    /// - `query_type`: 查询类型
    /// - `operation_name`: 操作名称（用于日志）
    /// - `f`: 执行查询的闭包
    ///
    /// # 返回
    ///
    /// 返回查询结果和性能指标
    fn execute_with_metrics<T, F>(
        &self,
        query_type: QueryType,
        operation_name: &str,
        f: F,
    ) -> HuGeResult<(T, QueryMetrics)>
    where
        F: FnOnce(&DbConn) -> HuGeResult<(T, usize)>,
    {
        let start = Instant::now();
        let conn = self.get_conn()?;

        let (result, rows_affected) = f(&conn)?;

        let duration = start.elapsed();
        let duration_us = duration.as_micros() as u64;
        let duration_ms = duration.as_millis() as u64;

        // 记录查询日志
        debug!(
            "数据库查询 [{}] {}: 耗时 {}μs ({}ms), 影响 {} 行",
            query_type, operation_name, duration_us, duration_ms, rows_affected
        );

        // 性能警告：超过 1s 记录警告
        if duration_ms > QUERY_SLOW_THRESHOLD_MS {
            warn!(
                "数据库查询 [{}] {} 耗时 {}ms，超过 {}ms 阈值",
                query_type, operation_name, duration_ms, QUERY_SLOW_THRESHOLD_MS
            );
        }

        let metrics = QueryMetrics { duration_us, rows_affected, query_type };

        Ok((result, metrics))
    }

    /// 获取记录总数（带性能监控）
    pub fn count_with_metrics(&self) -> HuGeResult<(i64, QueryMetrics)> {
        self.execute_with_metrics(QueryType::Select, "count", |conn| {
            let count: i64 =
                conn.query_row("SELECT COUNT(*) FROM screenshots", [], |row| row.get(0))?;
            Ok((count, 1))
        })
    }

    /// 搜索截图记录（带性能监控）
    pub fn search_with_metrics(
        &self,
        query: &str,
        limit: u32,
        offset: u32,
    ) -> HuGeResult<(Vec<ScreenshotRecord>, QueryMetrics)> {
        let search_pattern = format!("%{}%", Self::escape_like_pattern(query));

        self.execute_with_metrics(QueryType::Select, "search", |conn| {
            let mut stmt = conn.prepare(
                r#"
                SELECT id, created_at, file_path, thumbnail_path, width, height, file_size, ocr_text, tags, metadata, image_hash, is_pinned, ocr_cached_at, content_type, text_content
                FROM screenshots
                WHERE ocr_text LIKE ?1 ESCAPE '\' OR tags LIKE ?1 ESCAPE '\'
                ORDER BY is_pinned DESC, created_at DESC
                LIMIT ?2 OFFSET ?3
                "#,
            )?;

            let rows = stmt.query_map(params![search_pattern, limit, offset], |row| {
                Self::row_to_record(row)
            })?;

            let mut records = Vec::new();
            for row in rows {
                records.push(row?);
            }
            let count = records.len();
            Ok((records, count))
        })
    }
}

/// 截图记录更新
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ScreenshotRecordUpdate {
    pub ocr_text: Option<String>,
    pub tags: Option<String>,
    pub metadata: Option<String>,
    pub thumbnail_path: Option<String>,
    pub is_pinned: Option<bool>,
    pub ocr_cached_at: Option<String>,
}

/// 搜索参数
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchParams {
    pub query: Option<String>,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub tags: Option<Vec<String>>,
    pub sort_by: Option<String>,
    pub sort_order: Option<String>,
    pub offset: Option<u32>,
    pub limit: Option<u32>,
    pub pinned_only: Option<bool>,
}

/// 搜索结果
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchResult {
    pub items: Vec<ScreenshotRecord>,
    pub total: i64,
    pub has_more: bool,
}

/// 历史统计信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HistoryStats {
    pub total_count: i64,
    pub total_size: i64,
    pub today_count: i64,
    pub week_count: i64,
    pub month_count: i64,
    pub pinned_count: i64,
    pub uncached_ocr_count: i64,
}

/// 连接池状态
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PoolStatus {
    pub connections: u32,
    pub idle_connections: u32,
    pub max_size: u32,
}

/// 查询类型
///
/// **Validates: Requirements 4.3**
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum QueryType {
    Select,
    Insert,
    Update,
    Delete,
    Batch,
}

impl std::fmt::Display for QueryType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            QueryType::Select => write!(f, "SELECT"),
            QueryType::Insert => write!(f, "INSERT"),
            QueryType::Update => write!(f, "UPDATE"),
            QueryType::Delete => write!(f, "DELETE"),
            QueryType::Batch => write!(f, "BATCH"),
        }
    }
}

/// 查询性能指标
///
/// **Validates: Requirements 4.3, 4.6**
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct QueryMetrics {
    /// 查询耗时（微秒）
    pub duration_us: u64,
    /// 影响的行数
    pub rows_affected: usize,
    /// 查询类型
    pub query_type: QueryType,
}

/// 查询性能阈值（毫秒）
const QUERY_SLOW_THRESHOLD_MS: u64 = 1000;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_history_database_memory() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        let record = ScreenshotRecord {
            id: 0,
            created_at: "2024-01-01T00:00:00".to_string(),
            file_path: "/tmp/test.png".to_string(),
            thumbnail_path: None,
            width: 1920,
            height: 1080,
            file_size: Some(12345),
            ocr_text: Some("测试文本".to_string()),
            tags: Some(r#"["test"]"#.to_string()),
            metadata: None,
            image_hash: Some("abc123".to_string()),
            is_pinned: false,
            ocr_cached_at: None,
            content_type: "image".to_string(),
            text_content: None,
        };

        let id = db.insert(&record).unwrap();
        assert!(id > 0);

        let loaded = db.get(id).unwrap().unwrap();
        assert_eq!(loaded.file_path, "/tmp/test.png");
        assert_eq!(loaded.width, 1920);
        assert_eq!(loaded.image_hash, Some("abc123".to_string()));

        let count = db.count().unwrap();
        assert_eq!(count, 1);

        let deleted = db.delete(id).unwrap();
        assert!(deleted);

        let count = db.count().unwrap();
        assert_eq!(count, 0);
    }

    #[test]
    fn test_history_search() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        let record1 = ScreenshotRecord {
            id: 0,
            created_at: "2024-01-01T00:00:00".to_string(),
            file_path: "/tmp/test1.png".to_string(),
            thumbnail_path: None,
            width: 1920,
            height: 1080,
            file_size: None,
            ocr_text: Some("Hello World".to_string()),
            tags: None,
            metadata: None,
            image_hash: None,
            is_pinned: false,
            ocr_cached_at: None,
            content_type: "image".to_string(),
            text_content: None,
        };

        let record2 = ScreenshotRecord {
            id: 0,
            created_at: "2024-01-02T00:00:00".to_string(),
            file_path: "/tmp/test2.png".to_string(),
            thumbnail_path: None,
            width: 1920,
            height: 1080,
            file_size: None,
            ocr_text: Some("你好世界".to_string()),
            tags: None,
            metadata: None,
            image_hash: None,
            is_pinned: false,
            ocr_cached_at: None,
            content_type: "image".to_string(),
            text_content: None,
        };

        db.insert(&record1).unwrap();
        db.insert(&record2).unwrap();

        let results = db.search("Hello", 10, 0).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].file_path, "/tmp/test1.png");

        let results = db.search("世界", 10, 0).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].file_path, "/tmp/test2.png");
    }

    #[test]
    fn test_hash_deduplication() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        let record = ScreenshotRecord {
            image_hash: Some("unique_hash_123".to_string()),
            file_path: "/tmp/test.png".to_string(),
            width: 1920,
            height: 1080,
            ..Default::default()
        };

        db.insert(&record).unwrap();

        // 查找已存在的哈希
        let existing = db.find_by_hash("unique_hash_123").unwrap();
        assert!(existing.is_some());

        // 查找不存在的哈希
        let not_found = db.find_by_hash("nonexistent_hash").unwrap();
        assert!(not_found.is_none());
    }

    #[test]
    fn test_batch_operations() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        let records: Vec<ScreenshotRecord> = (0..5)
            .map(|i| ScreenshotRecord {
                file_path: format!("/tmp/test{}.png", i),
                width: 1920,
                height: 1080,
                ..Default::default()
            })
            .collect();

        // 批量插入
        let ids = db.insert_batch(&records).unwrap();
        assert_eq!(ids.len(), 5);

        // 验证插入
        let count = db.count().unwrap();
        assert_eq!(count, 5);

        // 批量删除
        let deleted = db.delete_batch(&ids[0..3]).unwrap();
        assert_eq!(deleted, 3);

        let count = db.count().unwrap();
        assert_eq!(count, 2);
    }

    #[test]
    fn test_pin_functionality() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        let record = ScreenshotRecord {
            file_path: "/tmp/test.png".to_string(),
            width: 1920,
            height: 1080,
            is_pinned: false,
            ..Default::default()
        };

        let id = db.insert(&record).unwrap();

        // 切换置顶
        db.toggle_pin(id).unwrap();
        let loaded = db.get(id).unwrap().unwrap();
        assert!(loaded.is_pinned);

        // 再次切换
        db.toggle_pin(id).unwrap();
        let loaded = db.get(id).unwrap().unwrap();
        assert!(!loaded.is_pinned);
    }

    #[test]
    fn test_ocr_cache() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        let record = ScreenshotRecord {
            file_path: "/tmp/test.png".to_string(),
            width: 1920,
            height: 1080,
            ocr_text: None,
            ..Default::default()
        };

        let id = db.insert(&record).unwrap();

        // 获取未缓存的记录
        let uncached = db.get_uncached_ocr_records(10).unwrap();
        assert_eq!(uncached.len(), 1);

        // 更新 OCR 缓存
        db.update_ocr_cache(id, "识别的文本").unwrap();

        // 再次获取未缓存的记录
        let uncached = db.get_uncached_ocr_records(10).unwrap();
        assert_eq!(uncached.len(), 0);

        // 验证 OCR 文本
        let loaded = db.get(id).unwrap().unwrap();
        assert_eq!(loaded.ocr_text, Some("识别的文本".to_string()));
        assert!(loaded.ocr_cached_at.is_some());
    }

    #[test]
    fn test_query_metrics() {
        let db = HistoryDatabase::open(":memory:").unwrap();

        // 插入测试数据
        let record = ScreenshotRecord {
            file_path: "/tmp/test.png".to_string(),
            width: 1920,
            height: 1080,
            ocr_text: Some("测试文本".to_string()),
            ..Default::default()
        };
        db.insert(&record).unwrap();

        // 测试 count_with_metrics
        let (count, metrics) = db.count_with_metrics().unwrap();
        assert_eq!(count, 1);
        assert_eq!(metrics.query_type, QueryType::Select);
        assert!(metrics.duration_us > 0);

        // 测试 search_with_metrics
        let (results, metrics) = db.search_with_metrics("测试", 10, 0).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(metrics.query_type, QueryType::Select);
        assert!(metrics.duration_us > 0);
    }

    #[test]
    fn test_pool_status() {
        let db = HistoryDatabase::open(":memory:").unwrap();
        let status = db.pool_status();

        assert_eq!(status.max_size, POOL_SIZE);
    }
}

// ============================================================================
// 属性测试 (Property-Based Testing)
// ============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use proptest::prelude::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    // 用于生成唯一的共享内存数据库名称
    static DB_COUNTER: AtomicU64 = AtomicU64::new(0);

    /// 创建一个唯一的共享内存数据库
    /// 使用 `file:memdb{id}?mode=memory&cache=shared` 格式
    /// 这样连接池中的所有连接都会共享同一个内存数据库
    fn create_test_db() -> HistoryDatabase {
        let id = DB_COUNTER.fetch_add(1, Ordering::SeqCst);
        let uri = format!("file:memdb{}?mode=memory&cache=shared", id);
        HistoryDatabase::open(&uri).unwrap()
    }

    // ========================================================================
    // Feature: rust-performance-optimization
    // Property 5: 批量操作原子性
    // Validates: Requirements 3.5
    // ========================================================================

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(50))]

        /// Property: 批量插入要么全部成功，要么全部失败
        ///
        /// 对于任意数量的记录，批量插入后数据库中的记录数应该等于插入的数量。
        #[test]
        fn prop_batch_insert_atomicity(
            count in 1usize..=20,
        ) {
            let db = create_test_db();

            // 创建测试记录
            let records: Vec<ScreenshotRecord> = (0..count)
                .map(|i| ScreenshotRecord {
                    file_path: format!("/tmp/test{}.png", i),
                    width: 1920,
                    height: 1080,
                    ..Default::default()
                })
                .collect();

            // 批量插入
            let ids = db.insert_batch(&records).unwrap();

            // 验证：返回的 ID 数量等于插入的记录数
            prop_assert_eq!(ids.len(), count,
                "返回的 ID 数量应该等于插入的记录数");

            // 验证：数据库中的记录数等于插入的数量
            let db_count = db.count().unwrap() as usize;
            prop_assert_eq!(db_count, count,
                "数据库中的记录数应该等于插入的数量");

            // 验证：所有记录都可以查询到
            for id in &ids {
                let record = db.get(*id).unwrap();
                prop_assert!(record.is_some(),
                    "插入的记录应该可以查询到");
            }
        }

        /// Property: 批量删除要么全部成功，要么全部失败
        ///
        /// 对于任意数量的记录，批量删除后数据库中不应该存在被删除的记录。
        #[test]
        fn prop_batch_delete_atomicity(
            total_count in 5usize..=20,
            delete_count in 1usize..=5,
        ) {
            let db = create_test_db();

            // 创建并插入测试记录
            let records: Vec<ScreenshotRecord> = (0..total_count)
                .map(|i| ScreenshotRecord {
                    file_path: format!("/tmp/test{}.png", i),
                    width: 1920,
                    height: 1080,
                    ..Default::default()
                })
                .collect();

            let ids = db.insert_batch(&records).unwrap();

            // 选择要删除的 ID
            let delete_count = delete_count.min(ids.len());
            let ids_to_delete: Vec<i64> = ids[0..delete_count].to_vec();

            // 批量删除
            let deleted = db.delete_batch(&ids_to_delete).unwrap();

            // 验证：删除的数量等于请求删除的数量
            prop_assert_eq!(deleted, delete_count,
                "删除的数量应该等于请求删除的数量");

            // 验证：数据库中的记录数正确
            let remaining = db.count().unwrap() as usize;
            prop_assert_eq!(remaining, total_count - delete_count,
                "剩余记录数应该等于总数减去删除数");

            // 验证：被删除的记录不存在
            for id in &ids_to_delete {
                let record = db.get(*id).unwrap();
                prop_assert!(record.is_none(),
                    "被删除的记录不应该存在");
            }

            // 验证：未删除的记录仍然存在
            for id in &ids[delete_count..] {
                let record = db.get(*id).unwrap();
                prop_assert!(record.is_some(),
                    "未删除的记录应该仍然存在");
            }
        }

        /// Property: 空批量操作不影响数据库状态
        ///
        /// 对于空的批量操作，数据库状态应该保持不变。
        #[test]
        fn prop_empty_batch_no_effect(
            initial_count in 0usize..=10,
        ) {
            let db = create_test_db();

            // 插入初始记录
            if initial_count > 0 {
                let records: Vec<ScreenshotRecord> = (0..initial_count)
                    .map(|i| ScreenshotRecord {
                        file_path: format!("/tmp/test{}.png", i),
                        width: 1920,
                        height: 1080,
                        ..Default::default()
                    })
                    .collect();
                db.insert_batch(&records).unwrap();
            }

            let count_before = db.count().unwrap();

            // 空批量插入
            let empty_records: Vec<ScreenshotRecord> = Vec::new();
            let ids = db.insert_batch(&empty_records).unwrap();
            prop_assert!(ids.is_empty(), "空批量插入应该返回空列表");

            // 空批量删除
            let empty_ids: Vec<i64> = Vec::new();
            let deleted = db.delete_batch(&empty_ids).unwrap();
            prop_assert_eq!(deleted, 0, "空批量删除应该返回 0");

            // 验证数据库状态不变
            let count_after = db.count().unwrap();
            prop_assert_eq!(count_before, count_after,
                "空批量操作不应该改变数据库状态");
        }

        /// Property: 批量插入的记录可以被正确检索
        ///
        /// 对于任意批量插入的记录，每条记录的字段值应该与插入时一致。
        #[test]
        fn prop_batch_insert_data_integrity(
            count in 1usize..=10,
            width in 100u32..=4000,
            height in 100u32..=4000,
        ) {
            let db = create_test_db();

            // 创建测试记录
            let records: Vec<ScreenshotRecord> = (0..count)
                .map(|i| ScreenshotRecord {
                    file_path: format!("/tmp/integrity_test_{}.png", i),
                    width,
                    height,
                    ocr_text: Some(format!("OCR 文本 {}", i)),
                    ..Default::default()
                })
                .collect();

            // 批量插入
            let ids = db.insert_batch(&records).unwrap();

            // 验证每条记录的数据完整性
            for (i, id) in ids.iter().enumerate() {
                let loaded = db.get(*id).unwrap().unwrap();

                prop_assert_eq!(loaded.file_path, format!("/tmp/integrity_test_{}.png", i),
                    "文件路径应该匹配");
                prop_assert_eq!(loaded.width, width,
                    "宽度应该匹配");
                prop_assert_eq!(loaded.height, height,
                    "高度应该匹配");
                prop_assert_eq!(loaded.ocr_text, Some(format!("OCR 文本 {}", i)),
                    "OCR 文本应该匹配");
            }
        }
    }
}
