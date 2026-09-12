const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const jsonHeaders = { ...corsHeaders, "Content-Type": "application/json" };

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return new Response(JSON.stringify({ error: "POST required" }), { status: 405, headers: jsonHeaders });
  }

  try {
    const body = await request.json();
    const glucose = Number(body.glucose);
    const trendArrow = String(body.trend_arrow || "→");
    const userText = String(body.message || "").trim();
    const history = Array.isArray(body.history) ? body.history.join(", ") : "unavailable";

    if (!userText || !Number.isFinite(glucose)) {
      return new Response(JSON.stringify({ error: "message and glucose are required" }), { status: 400, headers: jsonHeaders });
    }

    const groqKey = Deno.env.get("GROQ_API_KEY");
    if (!groqKey) {
      return new Response(JSON.stringify({ error: "GROQ_API_KEY is not configured" }), { status: 500, headers: jsonHeaders });
    }

    const state = glucose < 70 ? "low" : glucose <= 160 ? "in range" : glucose <= 220 ? "high" : "very high";
    const prompt = `The user asks: ${userText}

Current glucose: ${glucose} mg/dL
Trend arrow: ${trendArrow}
State: ${state}
Recent readings, oldest to newest: ${history}

Give a short, useful meal or snack recommendation based on the glucose and trend. Never give insulin or medication dosing advice. For a low, say to follow the user's established hypoglycemia plan and recheck; do not prescribe treatment. Return only valid JSON with this shape:
{"reply":"2-4 conversational sentences","show_macro":true,"macro":{"meal":"Lunch","carbs":"30-40g","protein":"25-30g","fat":"10-15g","note":"one sentence rationale","ideas":["idea 1","idea 2","idea 3"]}}`;

    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${groqKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: Deno.env.get("GROQ_MODEL") || "openai/gpt-oss-20b",
        messages: [
          { role: "system", content: "You are Sugar Buddy: concise, caring, dry, and practical. Do not diagnose or give medication instructions." },
          { role: "user", content: prompt },
        ],
        response_format: { type: "json_object" },
        max_tokens: 500,
      }),
    });
    if (!response.ok) {
      throw new Error(`Groq request failed: ${response.status}`);
    }

    const result = await response.json();
    const content = result.choices?.[0]?.message?.content;
    if (!content) throw new Error("Groq returned no recommendation");
    return new Response(content, { headers: jsonHeaders });
  } catch (error) {
    return new Response(JSON.stringify({ error: String(error) }), { status: 500, headers: jsonHeaders });
  }
});
