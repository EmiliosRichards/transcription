import pkg from 'pg';
const { Pool } = pkg;

// External database connection (Read-Only)
const externalDbConfig = {
  host: process.env.EXTERNAL_DB_HOST,
  database: process.env.EXTERNAL_DB_DATABASE,
  user: process.env.EXTERNAL_DB_USER,
  password: process.env.EXTERNAL_DB_PASSWORD,
  port: 5432,
  ssl: { rejectUnauthorized: false },
  connectionTimeoutMillis: 60000, // 60 seconds for connection
  idleTimeoutMillis: 300000, // 5 minutes idle timeout
  max: 10, // Increase connections
  statement_timeout: 300000, // 5 minute timeout for queries
  query_timeout: 300000 // 5 minute timeout for query execution
};

const hasExternalDbConfig = process.env.EXTERNAL_DB_HOST && 
  process.env.EXTERNAL_DB_DATABASE && 
  process.env.EXTERNAL_DB_USER && 
  process.env.EXTERNAL_DB_PASSWORD;

if (!hasExternalDbConfig) {
  console.warn("⚠️ External database environment variables not set. External database features will be disabled.");
}

export const externalPool = hasExternalDbConfig ? new Pool(externalDbConfig) : null;

// Helper function to check if external database is available
function checkExternalDb() {
  if (!externalPool) {
    throw new Error("External database is not configured. Please set EXTERNAL_DB_HOST, EXTERNAL_DB_DATABASE, EXTERNAL_DB_USER, and EXTERNAL_DB_PASSWORD environment variables.");
  }
}

// Whitelisted view selection (default to agent_data_v2)
// Keep explicit allow-list for safety; add new optimized views here as we introduce them.
const allowedAgentViews = new Set(['agent_data_v2', 'agent_data', 'agent_data_v3']);
const envView = (process.env.AGENT_DATA_VIEW || '').trim();
const AGENT_DATA_VIEW = allowedAgentViews.has(envView) ? envView : 'agent_data_v2';

// Type definitions for external database views
export interface AgentData {
  transaction_id?: string;    // Transaction ID for DISTINCT ON queries
  // Raw contact id from public.transactions (more reliable than contacts_id for rows without recordings)
  // Note: Not all queries populate this field; it's optional.
  transactions_contact_id?: string;
  transactions_fired_date: string;
  recordings_start_time: string;
  connections_duration: number;
  transactions_user_login: string;
  transactions_status: string;
  transactions_status_detail: string;
  transactions_type?: string; // From transactions.type (e.g. 'update', 'dial_result')
  recordings_started: string;
  recordings_stopped: string;
  recordings_location: string;
  connections_phone: string;
  contacts_campaign_id: string;
  contacts_id?: string;       // Contact ID for grouping
  // NEW: Test columns for Call-Details
  transactions_wrapup_time_sec?: number; // Wrapup time (not used for NBZ/VBZ)
  transactions_wait_time_sec?: number;   // WZ (s) - Wartezeit
  transactions_edit_time_sec?: number;   // NBZ (s) - Nachbearbeitungszeit
  transactions_pause_time_sec?: number;  // VBZ (s) - Vorbereitungszeit
  // NEW: Contact information fields
  contacts_firma?: string;   // Firmenname
  contacts_notiz?: string;   // Notizen
  contacts_name?: string;    // Ansprechpartner (Contact Person) - legacy
  contacts_full_name?: string;    // Vollständiger Ansprechpartner Name
}

export interface CampaignAgentReference {
  contacts_campaign_id: string;
  transactions_user_login: string;
}

export interface CampaignStateReference {
  contacts_campaign_id: string;
  transactions_status_detail: string;
  transactions_status: string; // 'declined', 'success', 'open'
}

export interface StageOpenContactsSummary {
  campaignId: string;
  stageId: string;
  stageKey: string;
  contactsInStage: number;
  futureFollowUpContacts: number;
  ownedContacts: number;
  blockedContactsUnion: number;
  dialfireAvailableContacts: number;
  openContactsLeft: number;
  untouchedOpenContactsLeft: number;
  assignedOpenContactsLeft: number;
  followUpAutoOpenContactsLeft: number;
  followUpPersonalOpenContactsLeft: number;
}

// Read-only query functions
export async function getAgentData(limit?: number, offset?: number, dateFrom?: string, dateTo?: string): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    // PERFORMANCE: Add reasonable default limit to prevent huge queries
    const limitClause = limit ? `LIMIT ${limit}` : 'LIMIT 10000';
    const offsetClause = offset ? `OFFSET ${offset}` : '';
    
    // SECURITY FIX: Use parameterized queries to prevent SQL injection
    const conditions = [];
    const params: any[] = [];
    
    if (dateFrom && dateTo) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      conditions.push(`transactions_fired_date <= $${params.length + 2}`);
      params.push(dateFrom, dateTo);
    } else if (dateFrom) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      params.push(dateFrom);
    } else if (dateTo) {
      conditions.push(`transactions_fired_date <= $${params.length + 1}`);
      params.push(dateTo);
    }
    
    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    
    // Use DISTINCT ON (transaction_id) for deduplication with parameterized query
    const query = `
      SELECT DISTINCT ON (transaction_id) *
      FROM ${AGENT_DATA_VIEW} 
      ${whereClause}
      ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
      ${limitClause} ${offsetClause}
    `;
    
    const result = await client.query(query, params);
    
    console.log(`🔍 OPTIMIZED: Found ${result.rows.length} unique records using DISTINCT ON (transaction_id) with LIMIT`);
    return result.rows;
  } finally {
    client.release();
  }
}

// PERFORMANCE: New optimized function for statistics with agent/project filtering
export async function getAgentDataForStatistics(
  agentNames: string[],
  projectNames?: string[],
  dateFrom?: string,
  dateTo?: string,
  limit: number = 5000
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const conditions = [];
    const params: any[] = [];
    
    // Agent filter with IN clause
    if (agentNames.length > 0) {
      conditions.push(`transactions_user_login = ANY($${params.length + 1})`);
      params.push(agentNames);
    }
    
    // Project filter with IN clause (if specified)
    if (projectNames && projectNames.length > 0) {
      conditions.push(`contacts_campaign_id = ANY($${params.length + 1})`);
      params.push(projectNames);
    }
    
    // Date range filter
    if (dateFrom && dateTo) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      conditions.push(`transactions_fired_date <= $${params.length + 2}`);
      params.push(dateFrom, dateTo);
    } else if (dateFrom) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      params.push(dateFrom);
    } else if (dateTo) {
      conditions.push(`transactions_fired_date <= $${params.length + 1}`);
      params.push(dateTo);
    }
    
    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    
    // Use DISTINCT ON for deduplication with performance limit
    const query = `
      SELECT DISTINCT ON (transaction_id) *
      FROM ${AGENT_DATA_VIEW} 
      ${whereClause}
      ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
      LIMIT ${limit}
    `;
    
    console.log(`🚀 STATISTICS OPTIMIZED: Executing optimized query for ${agentNames.length} agents, ${projectNames?.length || 'ALL'} projects, LIMIT ${limit}`);
    const result = await client.query(query, params);
    
    console.log(`🚀 STATISTICS OPTIMIZED: Found ${result.rows.length} records in single query`);
    return result.rows;
    
  } finally {
    client.release();
  }
}

// Optimized function for specific agent and project call details
export async function getAgentCallDetails(
  agentLogin: string, 
  campaignId: string, 
  dateFrom?: string, 
  dateTo?: string,
  limit: number = 0,  // 0 means no cap; we will rely on DISTINCT ON and filters
  timeFrom?: string,
  timeTo?: string,
  stageNames?: string[] // Kampagnenstufe ids (transactions.task_id)
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const normalizedAgent = agentLogin.trim();
    const normalizedCampaign = campaignId.trim();
    
    console.log(`🔍 getAgentCallDetails - Normalized filters:`);
    console.log(`   Agent: "${normalizedAgent}" (original: "${agentLogin}")`);
    console.log(`   Campaign: "${normalizedCampaign}" (original: "${campaignId}")`);
    console.log(`   Date range: ${dateFrom || 'any'} to ${dateTo || 'any'}`);
    console.log(`   Time range: ${timeFrom || 'start'} to ${timeTo || 'end'}`);
    
    const conditions = [
      `LOWER(TRIM(ad.transactions_user_login)) = LOWER(TRIM($1))`,
      `LOWER(TRIM(ad.contacts_campaign_id)) = LOWER(TRIM($2))`
    ];
    const params: any[] = [normalizedAgent, normalizedCampaign];
    
    if (dateFrom && dateTo) {
      // Date range query
      conditions.push(`ad.transactions_fired_date >= $${params.length + 1}`);
      conditions.push(`ad.transactions_fired_date <= $${params.length + 2}`);
      params.push(dateFrom, dateTo);
    } else if (dateFrom && !dateTo) {
      // Single date query (exact match)
      conditions.push(`ad.transactions_fired_date = $${params.length + 1}`);
      params.push(dateFrom);
    } else if (dateTo) {
      conditions.push(`ad.transactions_fired_date <= $${params.length + 1}`);
      params.push(dateTo);
    }

    // Optional time window (Europe/Berlin UI → UTC, HH:MM) using PostgreSQL's native timezone conversion
    // This handles DST transitions correctly even when date ranges cross clock changes
    if (timeFrom || timeTo) {
      // Treat full-day window as no-op
      const tf = timeFrom || '00:00';
      const tt = timeTo || '23:59';
      if (!(tf === '00:00' && (tt === '23:59' || tt === '24:00'))) {
        // Use PostgreSQL's timezone() function to convert UTC timestamp to Europe/Berlin local time
        // COALESCE gives us the best available timestamp; timezone() handles DST transitions correctly
        const berlinTimeExpr = `to_char(timezone('Europe/Berlin', COALESCE(ad.recordings_started::timestamp, ad.recordings_start_time::timestamp, ad.transactions_fired_date::timestamp)), 'HH24:MI')`;
        
        if (tf <= tt) {
          // Normal range (no midnight wrap-around)
          conditions.push(`${berlinTimeExpr} >= $${params.length + 1}`);
          params.push(tf);
          conditions.push(`${berlinTimeExpr} <= $${params.length + 1}`);
          params.push(tt);
        } else {
          // Wrap-around across midnight: time >= tf OR time <= tt
          conditions.push(`( ${berlinTimeExpr} >= $${params.length + 1} OR ${berlinTimeExpr} <= $${params.length + 2} )`);
          params.push(tf, tt);
        }
      }
    }

    // Optional stage filter (Kampagnenstufe) — derived from transactions.task_id
    if (stageNames && stageNames.length > 0) {
      conditions.push(`btrim(COALESCE(tr.task_id::text, '')) = ANY($${params.length + 1})`);
      params.push(stageNames);
    }
    
    // Use DISTINCT ON with robust unique key when transaction_id is missing
    const uniqueExpr = `COALESCE(ad.transaction_id::text, CONCAT_WS(':', ad.contacts_id::text, ad.contacts_campaign_id::text, ad.transactions_fired_date::text))`
    const limitClause = limit && limit > 0 ? `LIMIT ${limit}` : ''
    const result = await client.query(`
      SELECT DISTINCT ON (${uniqueExpr}) *
      FROM ${AGENT_DATA_VIEW} ad
      LEFT JOIN public.transactions tr ON tr.id::text = ad.transaction_id::text
      WHERE ${conditions.join(' AND ')}
    ORDER BY ${uniqueExpr},
             COALESCE(ad.recordings_started::timestamp, ad.recordings_start_time::timestamp, ad.transactions_fired_date::timestamp) DESC NULLS LAST,
             ad.connections_duration DESC NULLS LAST
      ${limitClause}
    `, params);
    
    if (result.rows.length === 0) {
      console.log(`❌ NO RESULTS for agent "${normalizedAgent}" + campaign "${normalizedCampaign}"`);
      console.log(`   💡 Possible causes:`);
      console.log(`      - Agent login mismatch (check transactions_user_login in database)`);
      console.log(`      - Campaign ID mismatch (check contacts_campaign_id in database)`);
      console.log(`      - Date range excludes all data (${dateFrom} to ${dateTo})`);
      console.log(`      - Time range excludes all data (${timeFrom || '00:00'} to ${timeTo || '23:59'} Berlin → UTC)`);
    } else {
      console.log(`✅ Found ${result.rows.length} unique records for agent "${normalizedAgent}" + campaign "${normalizedCampaign}"`);
    }
    
    return result.rows;
  } finally {
    client.release();
  }
}

// Optimized function: all call details for a specific agent across ALL campaigns/projects
export async function getAgentCallDetailsAllCampaigns(
  agentLogin: string,
  dateFrom?: string,
  dateTo?: string,
  limit: number = 0, // 0 means no cap
  timeFrom?: string,
  timeTo?: string
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const normalizedAgent = agentLogin.trim();
    const conditions = [
      `lower(btrim(transactions_user_login)) = lower(btrim($1))`,
    ];
    const params: any[] = [normalizedAgent];

    if (dateFrom && dateTo) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      conditions.push(`transactions_fired_date <= $${params.length + 2}`);
      params.push(dateFrom, dateTo);
    } else if (dateFrom && !dateTo) {
      conditions.push(`transactions_fired_date = $${params.length + 1}`);
      params.push(dateFrom);
    } else if (dateTo) {
      conditions.push(`transactions_fired_date <= $${params.length + 1}`);
      params.push(dateTo);
    }

    if (timeFrom || timeTo) {
      const tf = timeFrom || '00:00';
      const tt = timeTo || '23:59';
      if (!(tf === '00:00' && (tt === '23:59' || tt === '24:00'))) {
        const berlinTimeExpr = `to_char(timezone('Europe/Berlin', COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp)), 'HH24:MI')`;
        if (tf <= tt) {
          conditions.push(`${berlinTimeExpr} >= $${params.length + 1}`);
          params.push(tf);
          conditions.push(`${berlinTimeExpr} <= $${params.length + 1}`);
          params.push(tt);
        } else {
          conditions.push(`( ${berlinTimeExpr} >= $${params.length + 1} OR ${berlinTimeExpr} <= $${params.length + 2} )`);
          params.push(tf, tt);
        }
      }
    }

    const uniqueExpr = `COALESCE(transaction_id::text, CONCAT_WS(':', contacts_id::text, contacts_campaign_id::text, transactions_fired_date::text))`;
    const limitClause = limit && limit > 0 ? `LIMIT ${limit}` : '';

    const result = await client.query(
      `
      SELECT DISTINCT ON (${uniqueExpr}) *
      FROM ${AGENT_DATA_VIEW}
      WHERE ${conditions.join(' AND ')}
      ORDER BY ${uniqueExpr},
               COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp) DESC NULLS LAST,
               connections_duration DESC NULLS LAST
      ${limitClause}
      `,
      params
    );

    return result.rows;
  } finally {
    client.release();
  }
}

// Optimized function: call details for MANY agents across ALL campaigns/projects (one query).
export async function getAgentsCallDetailsAllCampaigns(
  agentLogins: string[],
  dateFrom?: string,
  dateTo?: string,
  limit: number = 0, // 0 means no cap
  timeFrom?: string,
  timeTo?: string
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const logins = (agentLogins || []).map(s => String(s || '').trim().toLowerCase()).filter(Boolean);
    if (logins.length === 0) return [];

    const conditions: string[] = [
      `lower(btrim(transactions_user_login)) = ANY($1)`,
    ];
    const params: any[] = [logins];

    if (dateFrom && dateTo) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      conditions.push(`transactions_fired_date <= $${params.length + 2}`);
      params.push(dateFrom, dateTo);
    } else if (dateFrom && !dateTo) {
      conditions.push(`transactions_fired_date = $${params.length + 1}`);
      params.push(dateFrom);
    } else if (dateTo) {
      conditions.push(`transactions_fired_date <= $${params.length + 1}`);
      params.push(dateTo);
    }

    if (timeFrom || timeTo) {
      const tf = timeFrom || '00:00';
      const tt = timeTo || '23:59';
      if (!(tf === '00:00' && (tt === '23:59' || tt === '24:00'))) {
        const berlinTimeExpr = `to_char(timezone('Europe/Berlin', COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp)), 'HH24:MI')`;
        if (tf <= tt) {
          conditions.push(`${berlinTimeExpr} >= $${params.length + 1}`);
          params.push(tf);
          conditions.push(`${berlinTimeExpr} <= $${params.length + 1}`);
          params.push(tt);
        } else {
          conditions.push(`( ${berlinTimeExpr} >= $${params.length + 1} OR ${berlinTimeExpr} <= $${params.length + 2} )`);
          params.push(tf, tt);
        }
      }
    }

    const uniqueExpr = `COALESCE(transaction_id::text, CONCAT_WS(':', contacts_id::text, contacts_campaign_id::text, transactions_fired_date::text))`;
    const limitClause = limit && limit > 0 ? `LIMIT ${limit}` : '';

    const result = await client.query(
      `
      SELECT DISTINCT ON (${uniqueExpr}) *
      FROM ${AGENT_DATA_VIEW}
      WHERE ${conditions.join(' AND ')}
      ORDER BY ${uniqueExpr},
               COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp) DESC NULLS LAST,
               connections_duration DESC NULLS LAST
      ${limitClause}
      `,
      params
    );

    return result.rows;
  } finally {
    client.release();
  }
}

// Optimized function for contact call details (across all agents/projects)
export async function getContactCallDetails(
  contactsId: string,
  dateFrom?: string,
  dateTo?: string,
  limit: number = 0,  // 0 means no cap
  timeFrom?: string,
  timeTo?: string
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const normalizedContactId = String(contactsId).trim();

    const conditions: string[] = [
      `contacts_id::text = $1`
    ];
    const params: any[] = [normalizedContactId];

    if (dateFrom && dateTo) {
      conditions.push(`transactions_fired_date >= $${params.length + 1}`);
      conditions.push(`transactions_fired_date <= $${params.length + 2}`);
      params.push(dateFrom, dateTo);
    } else if (dateFrom && !dateTo) {
      conditions.push(`transactions_fired_date = $${params.length + 1}`);
      params.push(dateFrom);
    } else if (dateTo) {
      conditions.push(`transactions_fired_date <= $${params.length + 1}`);
      params.push(dateTo);
    }

    // Optional time window (Europe/Berlin UI → UTC, HH:MM) using PostgreSQL's native timezone conversion
    if (timeFrom || timeTo) {
      const tf = timeFrom || '00:00';
      const tt = timeTo || '23:59';
      if (!(tf === '00:00' && (tt === '23:59' || tt === '24:00'))) {
        const berlinTimeExpr = `to_char(timezone('Europe/Berlin', COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp)), 'HH24:MI')`;

        if (tf <= tt) {
          conditions.push(`${berlinTimeExpr} >= $${params.length + 1}`);
          params.push(tf);
          conditions.push(`${berlinTimeExpr} <= $${params.length + 1}`);
          params.push(tt);
        } else {
          conditions.push(`( ${berlinTimeExpr} >= $${params.length + 1} OR ${berlinTimeExpr} <= $${params.length + 2} )`);
          params.push(tf, tt);
        }
      }
    }

    const uniqueExpr = `COALESCE(transaction_id::text, CONCAT_WS(':', contacts_id::text, contacts_campaign_id::text, transactions_fired_date::text))`;
    const limitClause = limit && limit > 0 ? `LIMIT ${limit}` : '';

    const result = await client.query(`
      SELECT DISTINCT ON (${uniqueExpr}) *
      FROM ${AGENT_DATA_VIEW}
      WHERE ${conditions.join(' AND ')}
      ORDER BY ${uniqueExpr},
               COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp) DESC NULLS LAST,
               connections_duration DESC NULLS LAST
      ${limitClause}
    `, params);

    return result.rows;
  } finally {
    client.release();
  }
}

// Fetch a single call by transaction id (fast path for call detail page).
// Note: If transaction_id is missing (our UI generates "row_<hash>"), this cannot be queried reliably.
export async function getCallDetailByTransactionId(
  transactionId: string
): Promise<(AgentData & { connections_duration_total?: number }) | null> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const tx = String(transactionId || '').trim();
    if (!tx) return null;
    if (tx.startsWith('row_')) return null;

    // For a given transaction_id there can be multiple rows (e.g. multiple connection segments).
    // We pick the "best" row but compute total connection duration across the transaction.
    const result = await client.query(
      `
        SELECT DISTINCT ON (transaction_id)
          *,
          SUM(COALESCE(connections_duration, 0)) OVER (PARTITION BY transaction_id) AS connections_duration_total
        FROM ${AGENT_DATA_VIEW}
        WHERE transaction_id::text = $1
        ORDER BY transaction_id,
                 COALESCE(recordings_started::timestamp, recordings_start_time::timestamp, transactions_fired_date::timestamp) DESC NULLS LAST,
                 connections_duration DESC NULLS LAST
        LIMIT 1
      `,
      [tx]
    );

    return (result.rows?.[0] as any) || null;
  } finally {
    client.release();
  }
}

export async function getCampaignAgentReference(): Promise<CampaignAgentReference[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    // Query agent_data_v2 directly instead of campaign_agent_reference_data view
    // The old view was built on agent_data which is missing recent data
    const result = await client.query(`
      SELECT DISTINCT contacts_campaign_id, transactions_user_login 
      FROM ${AGENT_DATA_VIEW}
      WHERE contacts_campaign_id IS NOT NULL 
      AND transactions_user_login IS NOT NULL
      ORDER BY transactions_user_login, contacts_campaign_id
    `);
    
    console.log(`📊 Campaign-Agent Reference: Found ${result.rows.length} distinct agent-campaign pairs from ${AGENT_DATA_VIEW}`);
    
    return result.rows;
  } finally {
    client.release();
  }
}

export async function getCampaignStateReference(campaignId?: string): Promise<CampaignStateReference[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    let query = `
      WITH latest_status_by_detail AS (
        SELECT DISTINCT ON (btrim(ad.contacts_campaign_id), btrim(ad.transactions_status_detail))
          btrim(ad.contacts_campaign_id) AS contacts_campaign_id,
          btrim(ad.transactions_status_detail) AS transactions_status_detail,
          btrim(ad.transactions_status) AS transactions_status
        FROM ${AGENT_DATA_VIEW} ad
        WHERE ad.contacts_campaign_id IS NOT NULL
          AND btrim(ad.contacts_campaign_id) <> ''
          AND ad.transactions_status_detail IS NOT NULL
          AND btrim(ad.transactions_status_detail) <> ''
          AND ad.transactions_status IN ('declined', 'success', 'open')
    `;
    
    const params: any[] = [];
    
    if (campaignId) {
      query += ` AND btrim(ad.contacts_campaign_id) = btrim($1)`;
      params.push(campaignId.trim());
    }
    
    query += `
        ORDER BY
          btrim(ad.contacts_campaign_id),
          btrim(ad.transactions_status_detail),
          COALESCE(
            NULLIF(ad.recordings_started::text, '')::timestamp,
            NULLIF(ad.recordings_start_time::text, '')::timestamp,
            NULLIF(ad.transactions_fired_date::text, '')::timestamp
          ) DESC NULLS LAST,
          ad.transactions_fired_date DESC NULLS LAST,
          CASE btrim(ad.transactions_status)
            WHEN 'success' THEN 3
            WHEN 'declined' THEN 2
            WHEN 'open' THEN 1
            ELSE 0
          END DESC
      )
      SELECT contacts_campaign_id, transactions_status_detail, transactions_status
      FROM latest_status_by_detail
      ORDER BY contacts_campaign_id, transactions_status, transactions_status_detail
    `;
    
    console.log(`🔍 Querying latest campaign outcome state from ${AGENT_DATA_VIEW} for ${campaignId || 'all campaigns'}`);
    const result = await client.query(query, params);
    console.log(`✅ Found ${result.rows.length} campaign state references`);
    
    return result.rows;
  } finally {
    client.release();
  }
}

// Bulk variant for multiple campaigns (used by Multi-Search to categorize outcomes deterministically per campaign).
export async function getCampaignStateReferenceForCampaigns(campaignIds: string[]): Promise<CampaignStateReference[]> {
  checkExternalDb();
  const ids = (campaignIds || []).map(s => String(s || '').trim()).filter(Boolean);
  if (ids.length === 0) return [];

  const client = await externalPool!.connect();
  try {
    const query = `
      WITH latest_status_by_detail AS (
        SELECT DISTINCT ON (btrim(ad.contacts_campaign_id), btrim(ad.transactions_status_detail))
          btrim(ad.contacts_campaign_id) AS contacts_campaign_id,
          btrim(ad.transactions_status_detail) AS transactions_status_detail,
          btrim(ad.transactions_status) AS transactions_status
        FROM ${AGENT_DATA_VIEW} ad
        WHERE btrim(ad.contacts_campaign_id) = ANY($1)
          AND ad.contacts_campaign_id IS NOT NULL
          AND btrim(ad.contacts_campaign_id) <> ''
          AND ad.transactions_status_detail IS NOT NULL
          AND btrim(ad.transactions_status_detail) <> ''
          AND ad.transactions_status IN ('declined', 'success', 'open')
        ORDER BY
          btrim(ad.contacts_campaign_id),
          btrim(ad.transactions_status_detail),
          COALESCE(
            NULLIF(ad.recordings_started::text, '')::timestamp,
            NULLIF(ad.recordings_start_time::text, '')::timestamp,
            NULLIF(ad.transactions_fired_date::text, '')::timestamp
          ) DESC NULLS LAST,
          ad.transactions_fired_date DESC NULLS LAST,
          CASE btrim(ad.transactions_status)
            WHEN 'success' THEN 3
            WHEN 'declined' THEN 2
            WHEN 'open' THEN 1
            ELSE 0
          END DESC
      )
      SELECT contacts_campaign_id, transactions_status_detail, transactions_status
      FROM latest_status_by_detail
      ORDER BY contacts_campaign_id, transactions_status, transactions_status_detail
    `;
    const result = await client.query(query, [ids]);
    return result.rows;
  } finally {
    client.release();
  }
}

export async function getStageOpenContactsSummary(stage?: string): Promise<StageOpenContactsSummary[]> {
  checkExternalDb();
  const normalizedStage = String(stage || '').trim();
  const client = await externalPool!.connect();

  try {
    const params: any[] = [];
    const stageFilterClause = normalizedStage
      ? `AND (
          btrim(COALESCE(c."$task"::text, '')) = $1
          OR btrim(COALESCE(c."$task_id"::text, '')) = $1
          OR btrim(COALESCE(c.anrufen_stufe::text, '')) = $1
        )`
      : '';

    if (normalizedStage) {
      params.push(normalizedStage);
    }

    const query = `
      WITH stage_contacts AS (
        SELECT
          COALESCE(
            NULLIF(btrim(COALESCE(c."$id"::text, '')), ''),
            NULLIF(btrim(COALESCE(c.id::text, '')), '')
          ) AS contact_key,
          btrim(COALESCE(c."$campaign_id"::text, '')) AS campaign_id,
          btrim(COALESCE(c."$task_id"::text, '')) AS stage_id,
          COALESCE(
            NULLIF(btrim(COALESCE(c."$task"::text, '')), ''),
            NULLIF(btrim(COALESCE(c.anrufen_stufe::text, '')), ''),
            NULLIF(btrim(COALESCE(c."$task_id"::text, '')), '')
          ) AS stage_key,
          lower(
            COALESCE(
              NULLIF(btrim(COALESCE(c."$$anrufen_status_detail"::text, '')), ''),
              NULLIF(btrim(COALESCE(c."$status_detail"::text, '')), '')
            )
          ) AS status_detail_key,
          lower(
            COALESCE(
              NULLIF(btrim(COALESCE(c."$$anrufen_status"::text, '')), ''),
              NULLIF(btrim(COALESCE(c."$status"::text, '')), '')
            )
          ) AS status_key,
          CASE
            WHEN NULLIF(btrim(COALESCE(c."$follow_up_date"::text, '')), '') IS NULL THEN FALSE
            WHEN c."$follow_up_date"::text ~ '^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}' THEN (c."$follow_up_date"::timestamptz) > now()
            ELSE FALSE
          END AS has_future_follow_up,
          NULLIF(btrim(COALESCE(c."$owner"::text, '')), '') IS NOT NULL AS has_owner
        FROM public.contacts c
        WHERE btrim(COALESCE(c."$campaign_id"::text, '')) <> ''
          AND COALESCE(
            NULLIF(btrim(COALESCE(c."$task"::text, '')), ''),
            NULLIF(btrim(COALESCE(c.anrufen_stufe::text, '')), ''),
            NULLIF(btrim(COALESCE(c."$task_id"::text, '')), '')
          ) IS NOT NULL
          AND COALESCE(
            NULLIF(btrim(COALESCE(c."$task"::text, '')), ''),
            NULLIF(btrim(COALESCE(c.anrufen_stufe::text, '')), ''),
            NULLIF(btrim(COALESCE(c."$task_id"::text, '')), '')
          ) <> ''
          ${stageFilterClause}
      )
      SELECT
        campaign_id AS "campaignId",
        stage_id AS "stageId",
        stage_key AS "stageKey",
        COUNT(*)::int AS "contactsInStage",
        COUNT(*) FILTER (WHERE has_future_follow_up)::int AS "futureFollowUpContacts",
        COUNT(*) FILTER (WHERE has_owner)::int AS "ownedContacts",
        COUNT(*) FILTER (WHERE has_future_follow_up OR has_owner)::int AS "blockedContactsUnion",
        COUNT(*) FILTER (WHERE NOT has_future_follow_up AND NOT has_owner)::int AS "dialfireAvailableContacts",
        COUNT(*) FILTER (WHERE status_key = 'open')::int AS "openContactsLeft",
        COUNT(*) FILTER (WHERE status_key = 'open' AND status_detail_key IN ('$none', 'none'))::int AS "untouchedOpenContactsLeft",
        COUNT(*) FILTER (WHERE status_key = 'open' AND status_detail_key IN ('$assigned', 'assigned'))::int AS "assignedOpenContactsLeft",
        COUNT(*) FILTER (WHERE status_key = 'open' AND status_detail_key IN ('$follow_up_auto', 'follow_up_auto'))::int AS "followUpAutoOpenContactsLeft",
        COUNT(*) FILTER (WHERE status_key = 'open' AND status_detail_key IN ('$follow_up_personal', 'follow_up_personal'))::int AS "followUpPersonalOpenContactsLeft"
      FROM stage_contacts
      WHERE contact_key IS NOT NULL
        AND contact_key <> ''
      GROUP BY campaign_id, stage_id, stage_key
      HAVING COUNT(*) > 0
      ORDER BY COUNT(*) DESC, campaign_id ASC, stage_key ASC, stage_id ASC
    `;

    const result = await client.query(query, params);
    return result.rows;
  } finally {
    client.release();
  }
}

export async function getOutcomeStatus(campaignId: string, outcomeDetail: string): Promise<string | null> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const query = `
      SELECT transactions_status
      FROM (
        SELECT DISTINCT ON (btrim(ad.contacts_campaign_id), btrim(ad.transactions_status_detail))
          btrim(ad.contacts_campaign_id) AS contacts_campaign_id,
          btrim(ad.transactions_status_detail) AS transactions_status_detail,
          btrim(ad.transactions_status) AS transactions_status
        FROM ${AGENT_DATA_VIEW} ad
        WHERE btrim(ad.contacts_campaign_id) = btrim($1)
          AND btrim(ad.transactions_status_detail) = btrim($2)
          AND ad.transactions_status IN ('declined', 'success', 'open')
        ORDER BY
          btrim(ad.contacts_campaign_id),
          btrim(ad.transactions_status_detail),
          COALESCE(
            NULLIF(ad.recordings_started::text, '')::timestamp,
            NULLIF(ad.recordings_start_time::text, '')::timestamp,
            NULLIF(ad.transactions_fired_date::text, '')::timestamp
          ) DESC NULLS LAST,
          ad.transactions_fired_date DESC NULLS LAST,
          CASE btrim(ad.transactions_status)
            WHEN 'success' THEN 3
            WHEN 'declined' THEN 2
            WHEN 'open' THEN 1
            ELSE 0
          END DESC
      ) latest_status
      LIMIT 1
    `;
    
    console.log(`🔍 Getting status for campaign ${campaignId}, outcome ${outcomeDetail}`);
    const result = await client.query(query, [campaignId.trim(), outcomeDetail.trim()]);
    
    if (result.rows.length > 0) {
      const status = result.rows[0].transactions_status;
      console.log(`✅ Found status: ${status} for ${outcomeDetail} in campaign ${campaignId}`);
      return status;
    } else {
      console.log(`❌ No status found for ${outcomeDetail} in campaign ${campaignId}`);
      return null;
    }
  } finally {
    client.release();
  }
}

export async function getAgentStats(
  agentLogin: string, 
  dateFrom?: string, 
  dateTo?: string
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    // Build WHERE conditions with parameterized queries
    let whereClause = `WHERE transactions_user_login = $1`;
    const params: any[] = [agentLogin];
    
    if (dateFrom && dateTo) {
      // Date range query
      whereClause += ` AND transactions_fired_date >= $${params.length + 1} AND transactions_fired_date <= $${params.length + 2}`;
      params.push(dateFrom, dateTo);
    } else if (dateFrom && !dateTo) {
      // Single date query (exact match)
      whereClause += ` AND transactions_fired_date = $${params.length + 1}`;
      params.push(dateFrom);
    } else if (dateTo) {
      whereClause += ` AND transactions_fired_date <= $${params.length + 1}`;
      params.push(dateTo);
    }
    
    // Use DISTINCT ON (transaction_id) for deduplication as specified by user
    const result = await client.query(`
      SELECT DISTINCT ON (transaction_id) *
      FROM ${AGENT_DATA_VIEW} 
      ${whereClause}
      ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
    `, params);
    
    console.log(`🔍 Found ${result.rows.length} unique records for agent "${agentLogin}" using DISTINCT ON (transaction_id)`);
    return result.rows;
  } finally {
    client.release();
  }
}

// Direct SQL query exactly as user specified
export async function getCallDetailsDirectly(
  agentName: string = 'Ihsan.Simseker',
  campaignId: string = '3F767KEPW4V73JZS',
  date: string = '2025-09-04'
): Promise<AgentData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    console.log(`🎯 DIRECT SQL: SELECT * FROM agent_data WHERE transactions_user_login = '${agentName}' AND transactions_fired_date = '${date}' AND contacts_campaign_id = '${campaignId}'`);
    
    const result = await client.query(`
      SELECT * FROM ${AGENT_DATA_VIEW} 
      WHERE LOWER(transactions_user_login) = LOWER($1) 
      AND transactions_fired_date = $2 
      AND contacts_campaign_id = $3
    `, [agentName, date, campaignId]);
    
    console.log(`✅ Direct SQL returned ${result.rows.length} records`);
    return result.rows;
  } finally {
    client.release();
  }
}

export async function getUniqueAgents(): Promise<string[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    console.log(`🔍 Loading agents from ${AGENT_DATA_VIEW} with 60-day window`);
    const result = await client.query(`
      SELECT DISTINCT transactions_user_login
      FROM ${AGENT_DATA_VIEW}
      WHERE transactions_user_login IS NOT NULL
        AND transactions_user_login != ''
        AND transactions_fired_date::date >= (CURRENT_DATE - INTERVAL '60 days')::date
      ORDER BY transactions_user_login
    `);
    
    console.log(`✅ Found ${result.rows.length} active agents from last 60 days`);
    
    // Deduplicate agents with different case variations
    // Keep only proper case: First letter uppercase, first letter after dot uppercase
    const agents = result.rows.map(row => row.transactions_user_login);
    const deduplicatedAgents = new Map<string, string>();
    
    for (const agent of agents) {
      const lowerKey = agent.toLowerCase();
      
      // Check if we already have this agent (case-insensitive)
      if (!deduplicatedAgents.has(lowerKey)) {
        deduplicatedAgents.set(lowerKey, agent);
      } else {
        // We have a duplicate - keep the one with proper case
        const existing = deduplicatedAgents.get(lowerKey)!;
        const proper = getProperCaseAgent(agent);
        const existingProper = getProperCaseAgent(existing);
        
        // If current agent has proper case, replace the existing one
        if (agent === proper && existing !== existingProper) {
          deduplicatedAgents.set(lowerKey, agent);
        }
      }
    }
    
    const finalAgents = Array.from(deduplicatedAgents.values()).sort();
    console.log(`🔧 Deduplicated ${agents.length} agents to ${finalAgents.length} (removed case duplicates)`);
    
    return finalAgents;
  } finally {
    client.release();
  }
}

/**
 * Find distinct agent login variants that match all tokens of a given name
 * within the last `days` days, optionally scoped to a campaign.
 * Token matching is case-insensitive and ignores separators like . _ - and spaces.
 */
export async function findSimilarAgentLogins(
  name: string,
  days: number = 60,
  campaignId?: string,
  mode: 'all' | 'any' = 'all',
  approx: boolean = true
): Promise<string[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    const safeDays = Math.max(1, Math.min(365, Math.floor(days || 60)));
    const rawTokens = String(name || '')
      .split(/[.\s_-]+/)
      .map(t => t.trim().toLowerCase())
      .filter(Boolean);

    if (rawTokens.length === 0) return [];

    // Expand common transliterations/diacritics for better matching
    const expandTokenVariants = (t: string): string[] => {
      const variants = new Set<string>();
      variants.add(t);
      if (!approx) return Array.from(variants);

      // Umlauts
      variants.add(t.replace(/ä/g, 'ae'));
      variants.add(t.replace(/ö/g, 'oe'));
      variants.add(t.replace(/ü/g, 'ue'));
      variants.add(t.replace(/ß/g, 'ss'));
      // Turkish characters
      variants.add(t.replace(/ş/g, 's'));
      variants.add(t.replace(/ğ/g, 'g'));
      variants.add(t.replace(/ı/g, 'i'));
      variants.add(t.replace(/İ/g, 'i'));
      // Remove diacritics broadly
      variants.add(t.normalize('NFD').replace(/[\u0300-\u036f]/g, ''));

      return Array.from(variants);
    };

    const tokenGroups = rawTokens.map(expandTokenVariants);

    let where = `transactions_user_login IS NOT NULL
                 AND transactions_user_login != ''
                 AND transactions_fired_date::date >= (CURRENT_DATE - INTERVAL '${safeDays} days')::date`;

    const params: any[] = [];

    if (campaignId && campaignId.trim() !== '') {
      params.push(campaignId.trim());
      where += ` AND contacts_campaign_id = $${params.length}`;
    }

    // Build token clauses
    const tokenClauses: string[] = [];
    for (const variants of tokenGroups) {
      if (variants.length === 0) continue;
      const variantClauses: string[] = [];
      for (const v of variants) {
        params.push(`%${v}%`);
        variantClauses.push(`LOWER(transactions_user_login) LIKE $${params.length}`);
      }
      if (variantClauses.length > 0) {
        tokenClauses.push(`(${variantClauses.join(' OR ')})`);
      }
    }

    if (tokenClauses.length > 0) {
      where += ` AND (${tokenClauses.join(mode === 'any' ? ' OR ' : ' AND ')})`;
    }

    const sql = `
      SELECT DISTINCT transactions_user_login
      FROM ${AGENT_DATA_VIEW}
      WHERE ${where}
      ORDER BY transactions_user_login
      LIMIT 200
    `;

    const result = await client.query(sql, params);
    return result.rows.map(r => r.transactions_user_login);
  } finally {
    client.release();
  }
}

// Helper function to convert agent name to proper case
function getProperCaseAgent(name: string): string {
  const parts = name.split('.');
  return parts.map(part => 
    part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()
  ).join('.');
}

export async function getUniqueCampaigns(): Promise<string[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    // Get valid campaign IDs from Google Sheets (active + archived).
    // IMPORTANT: These are the source of truth for what campaigns *should* be visible in the UI.
    // We then intersect with campaigns that actually have data in the external DB view.
    const { getSheetCampaignsFull } = await import('./google-sheets');
    const sheetCampaigns = await getSheetCampaignsFull();

    // Create case-insensitive lookup for campaign IDs (lower -> canonical).
    const validCampaignIdsMap = new Map<string, string>();
    for (const c of sheetCampaigns || []) {
      const id = String((c as any)?.campaign_id || '').trim();
      if (!id) continue;
      validCampaignIdsMap.set(id.toLowerCase(), id);
    }

    const sheetIdsLower = Array.from(validCampaignIdsMap.keys());
    console.log(`📊 Found ${sheetIdsLower.length} campaign_ids in Google Sheets`);

    if (sheetIdsLower.length === 0) {
      // Fallback: return DB campaigns (bounded) if Sheets are unavailable/misconfigured.
      const result = await client.query(`
        SELECT DISTINCT contacts_campaign_id
        FROM ${AGENT_DATA_VIEW}
        WHERE contacts_campaign_id IS NOT NULL
          AND contacts_campaign_id <> ''
        ORDER BY contacts_campaign_id
        LIMIT 2000
      `);
      return result.rows.map(r => String(r.contacts_campaign_id || '').trim()).filter(Boolean);
    }

    // Intersect sheet campaigns with DB campaigns WITHOUT an arbitrary LIMIT 200.
    // This avoids silently "missing" campaigns that exist in the DB but sort after the first 200.
    const result = await client.query(
      `
      SELECT DISTINCT contacts_campaign_id
      FROM ${AGENT_DATA_VIEW}
      WHERE contacts_campaign_id IS NOT NULL
        AND contacts_campaign_id <> ''
        AND lower(contacts_campaign_id) = ANY($1)
      ORDER BY contacts_campaign_id
      `,
      [sheetIdsLower]
    );

    const campaigns = result.rows
      .map(r => String(r.contacts_campaign_id || '').trim())
      .filter(Boolean)
      .map(id => validCampaignIdsMap.get(id.toLowerCase()) || id);

    console.log(`✅ Found ${campaigns.length} campaigns with data in DB that also exist in Google Sheets`);
    return campaigns;
  } finally {
    client.release();
  }
}

export interface AggregatedKpiData {
  week_start: string;
  total_calls: number;
  calls_reached: number;
  positive_outcomes: number;
  avg_call_duration_sec: number;
}

export async function getAggregatedKpis(
  agentLogins: string[],
  dateFrom: string,
  dateTo: string
): Promise<AggregatedKpiData[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    console.log(`📊 KPI Aggregation: Querying ${agentLogins.length} agents from ${dateFrom} to ${dateTo}`);
    
    // NOTE: Dialfire can create multiple "success" transaction rows for the same contact when an appointment is reset
    // and later marked as success again. To avoid double-counting, we count distinct contacts for successes.
    // We join public.transactions to access contact_id even when the agent_data view has no contacts_id (e.g. no recording).
    const query = `
      SELECT 
        DATE_TRUNC('week', ad.transactions_fired_date::date)::date AS week_start,
        COUNT(DISTINCT COALESCE(ad.transaction_id::text, CONCAT_WS(':', ad.contacts_id::text, ad.contacts_campaign_id::text, ad.transactions_fired_date::text))) AS total_calls,
        SUM(CASE WHEN ad.transactions_status = 'open' THEN 1 ELSE 0 END) AS calls_reached,
        COUNT(DISTINCT CASE
          WHEN ad.transactions_status = 'success'
          THEN COALESCE(tx.contact_id::text, ad.contacts_id::text, ad.transaction_id::text)
          ELSE NULL
        END) AS positive_outcomes,
        AVG(CASE WHEN ad.connections_duration > 0 THEN ad.connections_duration ELSE NULL END) AS avg_call_duration_sec
      FROM ${AGENT_DATA_VIEW} ad
      LEFT JOIN public.transactions tx ON tx.id::text = ad.transaction_id::text
      WHERE ad.transactions_user_login = ANY($1)
        AND ad.transactions_fired_date >= $2
        AND ad.transactions_fired_date <= $3
      GROUP BY DATE_TRUNC('week', ad.transactions_fired_date::date)
      ORDER BY week_start
    `;
    
    const result = await client.query(query, [agentLogins, dateFrom, dateTo]);
    console.log(`✅ KPI Aggregation: Returned ${result.rows.length} week(s) of aggregated data`);
    
    return result.rows.map(row => ({
      week_start: row.week_start,
      total_calls: parseInt(row.total_calls) || 0,
      calls_reached: parseInt(row.calls_reached) || 0,
      positive_outcomes: parseInt(row.positive_outcomes) || 0,
      avg_call_duration_sec: parseFloat(row.avg_call_duration_sec) || 0
    }));
  } finally {
    client.release();
  }
}

// Get monthly call trends for charts
export async function getMonthlyCallTrends(
  agentLogins: string[],
  year: number
): Promise<{ month: string; calls: number; projected?: boolean }[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    console.log(`📊 Monthly Trends: Querying ${agentLogins.length} agents for year ${year}`);
    
    const query = `
      SELECT 
        TO_CHAR(DATE_TRUNC('month', transactions_fired_date::date), 'Mon') AS month,
        EXTRACT(MONTH FROM transactions_fired_date::date) AS month_num,
        COUNT(DISTINCT COALESCE(transaction_id::text, CONCAT_WS(':', contacts_id::text, contacts_campaign_id::text, transactions_fired_date::text))) AS calls,
        MIN(transactions_fired_date::date) AS first_date,
        MAX(transactions_fired_date::date) AS last_date
      FROM ${AGENT_DATA_VIEW}
      WHERE transactions_user_login = ANY($1)
        AND EXTRACT(YEAR FROM transactions_fired_date::date) = $2
      GROUP BY DATE_TRUNC('month', transactions_fired_date::date), EXTRACT(MONTH FROM transactions_fired_date::date)
      ORDER BY month_num
    `;
    
    const result = await client.query(query, [agentLogins, year]);
    console.log(`✅ Monthly Trends: Returned ${result.rows.length} month(s) of data`);
    
    const now = new Date();
    const currentMonth = now.getMonth() + 1; // 1-12
    const currentYear = now.getFullYear();
    const currentDay = now.getDate();
    
    return result.rows.map(row => {
      const monthNum = parseInt(row.month_num);
      const actualCalls = parseInt(row.calls) || 0;
      
      // If this is the current month and we're in the current year, calculate projection
      if (monthNum === currentMonth && year === currentYear) {
        // Get the number of days in this month
        const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
        
        // Calculate daily average based on actual data so far
        const daysElapsed = currentDay;
        const dailyAverage = actualCalls / daysElapsed;
        
        // Project to full month
        const projectedCalls = Math.round(dailyAverage * daysInMonth);
        
        console.log(`📈 Projection for ${row.month}: ${actualCalls} actual calls over ${daysElapsed} days → ${projectedCalls} projected (${dailyAverage.toFixed(1)} calls/day)`);
        
        return {
          month: row.month,
          calls: projectedCalls,
          projected: true
        };
      }
      
      return {
        month: row.month,
        calls: actualCalls
      };
    });
  } finally {
    client.release();
  }
}

// Get outcome distribution for charts
export async function getOutcomeDistribution(
  agentLogins: string[],
  dateFrom: string,
  dateTo: string
): Promise<{ name: string; count: number; percentage: number }[]> {
  checkExternalDb();
  const client = await externalPool!.connect();
  try {
    console.log(`📊 Outcome Distribution: Querying ${agentLogins.length} agents from ${dateFrom} to ${dateTo}`);
    
    const query = `
      WITH total AS (
        SELECT COUNT(DISTINCT COALESCE(transaction_id::text, CONCAT_WS(':', contacts_id::text, contacts_campaign_id::text, transactions_fired_date::text)))::float AS total_count
        FROM ${AGENT_DATA_VIEW}
        WHERE transactions_user_login = ANY($1)
          AND transactions_fired_date >= $2
          AND transactions_fired_date <= $3
      ),
      outcomes AS (
        SELECT 
          CASE 
            WHEN transactions_status = 'success' THEN 'Success'
            WHEN transactions_status_detail IN ('cb', 'Callback') THEN 'Callback'
            WHEN transactions_status_detail IN ('na', 'No Answer') THEN 'No Answer'
            WHEN transactions_status = 'declined' THEN 'Declined'
            ELSE 'Other'
          END AS outcome_name,
          COUNT(DISTINCT COALESCE(transaction_id::text, CONCAT_WS(':', contacts_id::text, contacts_campaign_id::text, transactions_fired_date::text))) AS count
        FROM ${AGENT_DATA_VIEW}
        WHERE transactions_user_login = ANY($1)
          AND transactions_fired_date >= $2
          AND transactions_fired_date <= $3
        GROUP BY outcome_name
      )
      SELECT 
        outcome_name AS name,
        count,
        ROUND((count / total.total_count * 100)::numeric, 1) AS percentage
      FROM outcomes, total
      ORDER BY count DESC
    `;
    
    const result = await client.query(query, [agentLogins, dateFrom, dateTo]);
    console.log(`✅ Outcome Distribution: Returned ${result.rows.length} outcome types`);
    
    return result.rows.map(row => ({
      name: row.name,
      count: parseInt(row.count) || 0,
      percentage: parseFloat(row.percentage) || 0
    }));
  } finally {
    client.release();
  }
}