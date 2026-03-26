import { NextResponse } from "next/server";
import { env } from "~/env";

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

    const response = await fetch(env.BACKEND_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

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
    return NextResponse.json(
      { error: "Failed to analyze variant" },
      { status: 500 }
    );
  }
}