import { NextResponse } from "next/server";
import { env } from "~/env";

export const maxDuration = 300;

export async function POST(request: Request) {
  try {
    const body = await request.json() as {
      variant_position: number;
      alternative: string;
      genome: string;
      chromosome: string;
    };

    console.log("Proxying to Modal backend:", env.BACKEND_URL);
    console.log("Request body:", body);

    // Fetch genome sequence here in Next.js (always has internet)
    // This avoids Modal container network timeout issues with UCSC API
    const { variant_position, genome, chromosome } = body;
    const WINDOW_SIZE = 8192;
    const half = Math.floor(WINDOW_SIZE / 2);
    const start = Math.max(0, variant_position - 1 - half);
    const end = variant_position - 1 + half + 1;

    let sequence: string | undefined;

    try {
      console.log(`Fetching sequence from UCSC: ${chromosome}:${start}-${end} (${genome})`);
      const ucscUrl = `https://api.genome.ucsc.edu/getData/sequence?genome=${genome};chrom=${chromosome};start=${start};end=${end}`;
      const ucscRes = await fetch(ucscUrl, {
        signal: AbortSignal.timeout(15000), // 15 second timeout for UCSC
      });

      if (ucscRes.ok) {
        const ucscData = await ucscRes.json() as { dna?: string; error?: string };
        if (ucscData.dna) {
          sequence = ucscData.dna.toUpperCase();
          console.log(`Successfully fetched sequence, length: ${sequence.length}`);
        } else {
          console.warn("UCSC returned no DNA:", ucscData.error);
        }
      } else {
        console.warn("UCSC fetch failed with status:", ucscRes.status);
      }
    } catch (ucscError) {
      // Non-fatal: Modal will try to fetch it itself as fallback
      console.warn("UCSC fetch failed in proxy, Modal will attempt fallback:", ucscError);
    }

    // Send to Modal — with sequence attached if we got it
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 280000); // 280 sec

    const response = await fetch(env.BACKEND_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...body,
        ...(sequence ? { sequence } : {}), // Only attach if successfully fetched
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Modal backend error:", errorText);
      return NextResponse.json(
        { error: "Backend request failed", details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json() as Record<string, unknown>;
    return NextResponse.json(data);

  } catch (error) {
    console.error("Proxy error:", error);

    if (error instanceof Error && error.name === "AbortError") {
      return NextResponse.json(
        { error: "Request timed out — EVO2 model is warming up. Please try again in a moment." },
        { status: 504 }
      );
    }

    return NextResponse.json(
      { error: "Failed to analyze variant" },
      { status: 500 }
    );
  }
}