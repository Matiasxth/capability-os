import React, { useEffect, useState } from "react";
import sdk from "../../../sdk";
import ChannelCard from "./integrations/ChannelCard";

function stDot(v){if(["ready","enabled","ok","available","success"].includes(v))return"dot-success";if(v==="running"||v==="preparing")return"dot-running";if(["error","down","not_configured","disabled"].includes(v))return"dot-error";return"dot-neutral"}

/** Channel definitions — each renders as a ChannelCard */
const CHANNELS = [
  {
    name: "Telegram",
    sdkKey: "telegram",
    fields: [
      { key: "token", label: "Token", placeholder: "123456:ABC-DEF...", type: "token" },
      { key: "chat_id", label: "Chat ID", placeholder: "-1234567890" },
      { key: "user_ids", label: "Users", placeholder: "user_id_1, user_id_2" },
    ],
    buildConfig: (v) => ({ bot_token: v.token, default_chat_id: v.chat_id || "", allowed_user_ids: v.user_ids ? v.user_ids.split(",").map(s => s.trim()).filter(Boolean) : [] }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>@BotFather in Telegram &rarr; /newbot &rarr; copy token</li><li>Your User ID: /start to @userinfobot</li><li>Paste token + user ID above, Save, then Poll</li></ol>,
  },
  {
    name: "Slack",
    sdkKey: "slack",
    fields: [
      { key: "token", label: "Token", placeholder: "xoxb-...", type: "token" },
      { key: "channel_id", label: "Channel", placeholder: "C0123456789" },
      { key: "user_ids", label: "Users", placeholder: "U0123, U0456" },
    ],
    buildConfig: (v) => ({ bot_token: v.token, channel_id: v.channel_id, allowed_user_ids: v.user_ids ? v.user_ids.split(",").map(s => s.trim()).filter(Boolean) : [] }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Create a Slack App at api.slack.com/apps</li><li>Enable Bot Token Scopes: chat:write, channels:history, channels:read</li><li>Install to workspace, copy Bot User OAuth Token (xoxb-...)</li><li>Invite bot to channel, get Channel ID from channel details</li></ol>,
  },
  {
    name: "Discord",
    sdkKey: "discord",
    fields: [
      { key: "token", label: "Token", placeholder: "Bot token...", type: "token" },
      { key: "channel_id", label: "Channel", placeholder: "Channel ID" },
      { key: "guild_id", label: "Guild", placeholder: "Guild/Server ID" },
      { key: "user_ids", label: "Users", placeholder: "user_id_1, user_id_2" },
    ],
    buildConfig: (v) => ({ bot_token: v.token, channel_id: v.channel_id, guild_id: v.guild_id, allowed_user_ids: v.user_ids ? v.user_ids.split(",").map(s => s.trim()).filter(Boolean) : [] }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Go to discord.com/developers/applications &rarr; New Application</li><li>Bot tab &rarr; Reset Token &rarr; copy bot token</li><li>Enable MESSAGE CONTENT INTENT</li><li>OAuth2 &rarr; URL Generator &rarr; scopes: bot &rarr; permissions: Send Messages, Read Message History</li><li>Use generated URL to invite bot to your server</li><li>Right-click channel &rarr; Copy Channel ID (enable Developer Mode in settings)</li></ol>,
  },
  {
    name: "Signal",
    sdkKey: "signal",
    fields: [
      { key: "token", label: "API URL", placeholder: "http://localhost:8080", type: "token" },
      { key: "phone", label: "Phone", placeholder: "+1234567890" },
      { key: "user_ids", label: "Recipients", placeholder: "+1234, +5678" },
    ],
    buildConfig: (v) => ({ api_url: v.token, phone_number: v.phone, allowed_recipients: v.user_ids ? v.user_ids.split(",").map(s => s.trim()).filter(Boolean) : [] }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Run signal-cli-rest-api Docker container</li><li>Register or link your phone number</li><li>Enter the API URL and phone number above</li></ol>,
  },
  {
    name: "Matrix",
    sdkKey: "matrix",
    fields: [
      { key: "token", label: "Token", placeholder: "syt_...", type: "token" },
      { key: "homeserver", label: "Server", placeholder: "https://matrix.org" },
      { key: "room_id", label: "Room", placeholder: "!abc123:matrix.org" },
    ],
    buildConfig: (v) => ({ access_token: v.token, homeserver_url: v.homeserver, room_id: v.room_id }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Create a Matrix account (e.g. on matrix.org)</li><li>Generate an access token from Element settings</li><li>Get the Room ID from room settings &rarr; Advanced</li></ol>,
  },
  {
    name: "Teams",
    sdkKey: "teams",
    fields: [
      { key: "token", label: "App ID", placeholder: "xxxxxxxx-xxxx-...", type: "token" },
      { key: "secret", label: "Secret", placeholder: "App secret" },
      { key: "tenant_id", label: "Tenant", placeholder: "Tenant ID" },
    ],
    buildConfig: (v) => ({ app_id: v.token, app_secret: v.secret, tenant_id: v.tenant_id }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Register an app in Azure AD</li><li>Configure Bot Channel Registration</li><li>Copy App ID, Secret, and Tenant ID</li></ol>,
  },
  {
    name: "Email",
    sdkKey: "email",
    fields: [
      { key: "token", label: "Password", placeholder: "IMAP password or app password", type: "token" },
      { key: "imap_host", label: "IMAP", placeholder: "imap.gmail.com" },
      { key: "smtp_host", label: "SMTP", placeholder: "smtp.gmail.com" },
      { key: "email", label: "Email", placeholder: "user@example.com" },
    ],
    buildConfig: (v) => ({ password: v.token, imap_host: v.imap_host, smtp_host: v.smtp_host, email_address: v.email }),
    guide: <ol style={{margin:"4px 0",paddingLeft:16,lineHeight:1.6}}><li>Enable IMAP in your email settings</li><li>For Gmail: generate an App Password</li><li>Enter IMAP/SMTP hosts and credentials</li></ol>,
  },
  {
    name: "Webhook",
    sdkKey: "webhook",
    fields: [
      { key: "token", label: "Secret", placeholder: "Webhook secret (optional)", type: "token" },
      { key: "callback_url", label: "URL", placeholder: "https://your-app.com/webhook" },
    ],
    buildConfig: (v) => ({ secret: v.token, callback_url: v.callback_url }),
    guide: "Configure an incoming webhook endpoint. Messages POSTed to /integrations/webhook/receive will be processed by CapOS.",
  },
];

const KNOWN_CONNECTORS = ["telegram_bot_connector","slack_bot_connector","discord_bot_connector","whatsapp_web_connector"];

export default function IntegrationsSection({ settings, setSettings, integrations, saving, toast, act }) {
  const [expandedIntegration, setExpandedIntegration] = useState(null);
  const [wspSession, setWspSession] = useState(null);
  const [wspQR, setWspQR] = useState(null);
  const [wspConnecting, setWspConnecting] = useState(false);

  useEffect(() => {
    sdk.integrations.whatsapp.status().then(r => { setWspSession(r); if (r.active) setWspQR(null) }).catch(() => setWspSession({ active: false }));
  }, []);

  // Poll for WhatsApp auth when QR is visible
  useEffect(() => {
    if (!wspQR) return;
    const id = setInterval(() => {
      sdk.integrations.whatsapp.status().then(r => {
        if (r.connected || r.status === "connected") { setWspQR(null); setWspSession({ active: true }); toast("WhatsApp connected") }
        else if (r.qr_image) { setWspQR(r.qr_image) }
        setWspSession(r);
      }).catch(() => {});
    }, 3000);
    return () => clearInterval(id);
  }, [wspQR]);

  const wsp = wspSession || {};

  return (<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <h2>Integrations</h2>

    {/* -- WhatsApp Hub (custom — has QR, backend selector) -- */}
    {(() => {const wb=settings?.whatsapp?.backend||"browser";const isOfficial=wb==="official";const wspExp=expandedIntegration==="whatsapp";return<div className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"10px 14px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(wspExp?null:"whatsapp")}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:4}}>{wspExp?"\u25BC":"\u25B6"}</span>
        <span style={{fontSize:16,marginRight:4}}>&#128172;</span>
        <span style={{fontSize:13,fontWeight:700,flex:1}}>WhatsApp</span>
        <span className={`dot ${wsp.active?"dot-success":"dot-neutral"}`} style={{marginRight:4}}/>
        <span style={{fontSize:10,color:wsp.active?"var(--success)":"var(--text-muted)",fontWeight:600}}>{wsp.active?"Online":"Offline"}</span>
      </div>
      {wspExp&&<div style={{padding:"0 14px 14px"}}>
        <div style={{background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:8,padding:10,marginBottom:8}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>Backend</div>
          <div style={{display:"flex",gap:4}}>
            {[{id:"browser",label:"Browser",desc:"Puppeteer"},{id:"baileys",label:"Baileys",desc:"Node.js"},{id:"official",label:"Official",desc:"Cloud API"}].map(b=><button key={b.id} onClick={async()=>{try{await sdk.integrations.whatsapp.switchBackend(b.id);const s=await sdk.system.settings.get();setSettings(s.settings||s);setWspSession({active:false});setWspQR(null);toast("Backend: "+b.label)}catch(err){toast(err.message,"error")}}} style={{flex:1,height:36,border:wb===b.id?"1px solid var(--accent)":"1px solid var(--border)",borderRadius:6,background:wb===b.id?"var(--accent-dim)":"var(--bg-input)",color:wb===b.id?"var(--accent)":"var(--text-dim)",fontSize:10,fontWeight:wb===b.id?700:500,cursor:"pointer",transition:"all 0.2s",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:1,padding:2}}><span>{b.label}</span><span style={{fontSize:8,opacity:0.6}}>{b.desc}</span></button>)}
          </div>
        </div>
        {isOfficial&&<div style={{background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:8,padding:10,marginBottom:8}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>API Configuration</div>
          {[{label:"Access Token",key:"access_token",type:"password",placeholder:"EAA..."},{label:"Phone Number ID",key:"phone_number_id",placeholder:"1234567890"},{label:"Verify Token",key:"verify_token",placeholder:"my_secret_token"}].map(f=>
            <React.Fragment key={f.key}><label style={{display:"block",fontSize:10,color:"var(--text-dim)",marginBottom:2}}>{f.label}</label>
            <input type={f.type||"text"} defaultValue={settings?.whatsapp?.official?.[f.key]||""} style={{width:"100%",height:28,fontSize:11,background:"var(--bg-elevated)",border:"1px solid var(--border)",borderRadius:4,color:"var(--text)",padding:"0 8px",marginBottom:6}} onBlur={e=>sdk.integrations.whatsapp.configure({official:{...(settings?.whatsapp?.official||{}),[f.key]:e.target.value}}).then(()=>toast("Saved")).catch(()=>{})} placeholder={f.placeholder}/></React.Fragment>
          )}
        </div>}
        {wspQR&&<div style={{background:"var(--bg-input)",border:"1px solid var(--border)",borderRadius:8,padding:10,marginBottom:8}}>
          <div style={{fontSize:9,textTransform:"uppercase",letterSpacing:2,color:"var(--accent)",marginBottom:6,fontWeight:600}}>Scan QR Code</div>
          <div style={{padding:12,background:"#ffffff",borderRadius:8,textAlign:"center",marginBottom:8}}><img src={wspQR} alt="QR" style={{width:180,height:180,imageRendering:"pixelated"}}/><div style={{fontSize:10,color:"#333",marginTop:6}}>Open WhatsApp &gt; Linked Devices &gt; Scan</div></div>
          <div style={{display:"flex",gap:4}}>
            <button style={{flex:1,height:28,fontSize:10}} onClick={async()=>{try{const r=await sdk.integrations.whatsapp.status();if(r.connected||r.active||r.status==="connected"){setWspQR(null);setWspSession({active:true});toast("Connected")}else if(r.qr_image)setWspQR(r.qr_image)}catch{}}}>Check Status</button>
            <button style={{flex:1,height:28,fontSize:10}} onClick={async()=>{await sdk.integrations.whatsapp.stop();setWspQR(null)}}>Cancel</button>
          </div>
        </div>}
        {!wspQR&&<div style={{display:"flex",gap:6}}>
          {!wsp.active?<button className="btn-primary" disabled={wspConnecting} onClick={async()=>{setWspConnecting(true);try{const r=await sdk.integrations.whatsapp.start();const c=r.connected||r.status==="connected";setWspSession({...wsp,...r,active:c});if(r.status==="error")toast(r.error||"Connection failed","error");else if(r.qr_image)setWspQR(r.qr_image);if(c){toast("WhatsApp connected");setWspQR(null)}}catch(e){toast(e.message,"error")}finally{setWspConnecting(false)}}} style={{flex:1,height:32,fontSize:11}}>{wspConnecting?"Connecting...":"Connect"}</button>
          :<button className="btn-danger" onClick={()=>act(async()=>{await sdk.integrations.whatsapp.stop();setWspSession({active:false});setWspQR(null)},"Disconnected")} style={{flex:1,height:32,fontSize:11}}>Disconnect</button>}
        </div>}
      </div>}
    </div>})()}

    {/* Other integrations (non-channel) */}
    {integrations.filter(i => !KNOWN_CONNECTORS.includes(i.id)).map(i => {const exp=expandedIntegration===i.id;return<div key={i.id} className="card" style={{padding:0,overflow:"hidden"}}>
      <div className="item-row" style={{padding:"8px 10px",cursor:"pointer"}} onClick={()=>setExpandedIntegration(exp?null:i.id)}>
        <span style={{fontSize:10,color:"var(--text-muted)",marginRight:2}}>{exp?"\u25BC":"\u25B6"}</span>
        <span className={`dot ${stDot(i.status)}`} style={{marginRight:3}}/>
        <span style={{fontSize:11,fontWeight:500,flex:1}}>{i.name||i.id}</span>
        <span className="dim" style={{fontSize:10,marginLeft:3}}>{i.status}</span>
      </div>
      {exp&&<div style={{padding:"6px 10px",borderTop:"1px solid rgba(255,255,255,0.04)",fontSize:10,color:"var(--text-muted)"}}>No additional settings for this integration.</div>}
    </div>})}

    {/* All channels via ChannelCard */}
    {CHANNELS.map(ch => (
      <ChannelCard
        key={ch.sdkKey}
        name={ch.name}
        sdk={sdk.integrations[ch.sdkKey]}
        fields={ch.fields}
        buildConfig={ch.buildConfig}
        guide={ch.guide}
        saving={saving}
        toast={toast}
        act={act}
      />
    ))}
  </div>);
}
