/// executor.rs — places real orders on Polymarket CLOB
///
/// Two auth layers Polymarket requires:
///   L1: EIP-712 signature on the order struct (proves you own the wallet)
///   L2: HMAC-SHA256 on the request (proves you own the API key)

use std::env;
use std::time::{SystemTime, UNIX_EPOCH};

use alloy_primitives::{Address, U256};
use alloy_signer::Signer;
use alloy_signer_local::PrivateKeySigner;
use alloy_sol_types::{eip712_domain, sol, SolStruct};
use base64::Engine;
use hmac::{Hmac, Mac};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use sha2::Sha256;

// ---------------------------------------------------------------------------
// EIP-712 order struct — must match Polymarket's on-chain Exchange contract
// ---------------------------------------------------------------------------
sol! {
    struct Order {
        uint256 salt;
        address maker;
        address signer;
        address taker;
        uint256 tokenId;
        uint256 makerAmount;
        uint256 takerAmount;
        uint256 expiration;
        uint256 nonce;
        uint256 feeRateBps;
        uint8   side;
        uint8   signatureType;
    }
}

// Polymarket CTF Exchange contract on Polygon
const CTF_EXCHANGE: &str = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e";
const CLOB_HOST:    &str = "https://clob.polymarket.com";

// BUY = 0, SELL = 1
pub const SIDE_BUY:  u8 = 0;
pub const SIDE_SELL: u8 = 1;

// ---------------------------------------------------------------------------
// JSON shapes for the CLOB REST API
// ---------------------------------------------------------------------------
#[derive(Serialize)]
struct PostOrderBody {
    order:      OrderFields,
    owner:      String,
    orderType:  String,   // "GTC" | "FOK" | "GTD"
}

#[derive(Serialize)]
struct OrderFields {
    salt:          String,
    maker:         String,
    signer:        String,
    taker:         String,
    tokenId:       String,
    makerAmount:   String,
    takerAmount:   String,
    expiration:    String,
    nonce:         String,
    feeRateBps:    String,
    side:          String,
    signatureType: String,
    signature:     String,
}

#[derive(Deserialize, Debug)]
struct ApiResponse {
    #[serde(rename = "orderID")]
    order_id: Option<String>,
    #[serde(rename = "errorMsg")]
    error:    Option<String>,
}

// ---------------------------------------------------------------------------
// Executor — holds auth material, exposes place_order()
// ---------------------------------------------------------------------------
pub struct Executor {
    signer:         PrivateKeySigner,
    http:           Client,
    api_key:        String,
    api_secret:     String,   // base64-encoded, as Polymarket provides it
    api_passphrase: String,
}

impl Executor {
    /// Load credentials from environment variables:
    ///   PRIVATE_KEY          — hex-encoded Ethereum private key (no 0x prefix needed)
    ///   POLYMARKET_API_KEY   — from Polymarket API dashboard
    ///   POLYMARKET_SECRET    — base64-encoded secret
    ///   POLYMARKET_PASSPHRASE
    pub fn from_env() -> anyhow::Result<Self> {
        let raw_key = env::var("PRIVATE_KEY")?;
        let signer: PrivateKeySigner = raw_key.trim().parse()?;
        Ok(Self {
            signer,
            http:           Client::new(),
            api_key:        env::var("POLYMARKET_API_KEY")?,
            api_secret:     env::var("POLYMARKET_SECRET")?,
            api_passphrase: env::var("POLYMARKET_PASSPHRASE")?,
        })
    }

    /// Place a limit order.
    ///
    /// * `token_id`   — the CTF token ID for the outcome (YES or NO token)
    /// * `side`       — SIDE_BUY or SIDE_SELL
    /// * `price`      — limit price in [0.01, 0.99]
    /// * `size_usdc`  — how many USDC to spend (BUY) or shares to sell (SELL)
    ///
    /// Returns the Polymarket order ID on success.
    pub async fn place_order(
        &self,
        token_id:  &str,
        side:      u8,
        price:     f64,
        size_usdc: f64,
    ) -> anyhow::Result<String> {
        let maker = self.signer.address();

        // Polymarket uses 6-decimal fixed-point (USDC has 6 decimals).
        // makerAmount = what you give;  takerAmount = what you expect back.
        let (maker_amount_u64, taker_amount_u64) = if side == SIDE_BUY {
            // Buying: you give USDC, you get shares
            let usdc_amount  = (size_usdc * 1_000_000.0).round() as u64;
            let share_amount = (size_usdc / price * 1_000_000.0).round() as u64;
            (usdc_amount, share_amount)
        } else {
            // Selling: you give shares, you get USDC
            let share_amount = (size_usdc * 1_000_000.0).round() as u64;
            let usdc_amount  = (size_usdc * price * 1_000_000.0).round() as u64;
            (share_amount, usdc_amount)
        };

        // Use current time as a random salt — cheap but sufficient
        let now = unix_now();
        let salt = U256::from(now);

        let expiration = now + 86_400; // order lives for 24 hours

        let token_id_u256: U256 = token_id.parse()
            .map_err(|_| anyhow::anyhow!("invalid token_id: {token_id}"))?;

        // Build the EIP-712 struct
        let order_struct = Order {
            salt:          salt,
            maker:         maker,
            signer:        maker,
            taker:         Address::ZERO,   // 0x00… means anyone can fill
            tokenId:       token_id_u256,
            makerAmount:   U256::from(maker_amount_u64),
            takerAmount:   U256::from(taker_amount_u64),
            expiration:    U256::from(expiration),
            nonce:         U256::ZERO,
            feeRateBps:    U256::ZERO,
            side:          side,
            signatureType: 0,               // 0 = EOA (plain private key)
        };

        // EIP-712 domain for Polymarket's exchange contract
        let domain = eip712_domain! {
            name:               "Polymarket CTF Exchange",
            version:            "1",
            chain_id:           137u64,
            verifying_contract: CTF_EXCHANGE.parse::<Address>()?,
        };

        // Hash the struct then sign it — this is what the contract verifies on-chain
        let signing_hash = order_struct.eip712_signing_hash(&domain);
        let signature    = self.signer.sign_hash(&signing_hash).await?;

        // Serialize into the JSON shape the CLOB API expects
        let fields = OrderFields {
            salt:          salt.to_string(),
            maker:         format!("{maker:#x}"),
            signer:        format!("{maker:#x}"),
            taker:         format!("{:#x}", Address::ZERO),
            tokenId:       token_id.to_string(),
            makerAmount:   maker_amount_u64.to_string(),
            takerAmount:   taker_amount_u64.to_string(),
            expiration:    expiration.to_string(),
            nonce:         "0".to_string(),
            feeRateBps:    "0".to_string(),
            side:          side.to_string(),
            signatureType: "0".to_string(),
            signature:     format!("0x{}", hex::encode(signature.as_bytes())),
        };

        let payload = PostOrderBody {
            order:     fields,
            owner:     format!("{maker:#x}"),
            orderType: "GTC".to_string(),
        };

        // ---------------------------------------------------------------
        // L2 auth: HMAC-SHA256(timestamp + "POST" + "/order" + body)
        // The secret Polymarket gives you is base64-encoded.
        // ---------------------------------------------------------------
        let timestamp = now.to_string();
        let body_str  = serde_json::to_string(&payload)?;
        let message   = format!("{}POST/order{}", timestamp, body_str);
        let hmac_sig  = hmac_base64(&self.api_secret, &message)?;

        let resp = self.http
            .post(format!("{CLOB_HOST}/order"))
            .header("POLY_ADDRESS",    format!("{maker:#x}"))
            .header("POLY_SIGNATURE",  hmac_sig)
            .header("POLY_TIMESTAMP",  &timestamp)
            .header("POLY_API_KEY",    &self.api_key)
            .header("POLY_PASSPHRASE", &self.api_passphrase)
            .json(&payload)
            .send()
            .await?;

        let api_resp: ApiResponse = resp.json().await?;

        match api_resp.order_id {
            Some(id) => Ok(id),
            None => Err(anyhow::anyhow!(
                "CLOB API error: {}",
                api_resp.error.unwrap_or_else(|| "unknown".into())
            )),
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("time went backwards")
        .as_secs()
}

/// HMAC-SHA256, output as base64 — matches what Polymarket expects
fn hmac_base64(b64_secret: &str, message: &str) -> anyhow::Result<String> {
    let secret = base64::engine::general_purpose::STANDARD
        .decode(b64_secret)
        .map_err(|e| anyhow::anyhow!("bad API secret (expected base64): {e}"))?;

    let mut mac = Hmac::<Sha256>::new_from_slice(&secret)
        .map_err(|e| anyhow::anyhow!("HMAC init failed: {e}"))?;
    mac.update(message.as_bytes());

    let result = mac.finalize().into_bytes();
    Ok(base64::engine::general_purpose::STANDARD.encode(result))
}
