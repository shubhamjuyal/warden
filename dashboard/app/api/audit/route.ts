import { listAudit } from "../../lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const audit = await listAudit();
    return Response.json(audit);
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return Response.json({ error: message }, { status: 500 });
  }
}
