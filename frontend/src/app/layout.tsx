import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Medical Literature Assistant",
  description:
    "A research-only assistant for exploring medical literature. Not a substitute for professional medical advice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 antialiased">
        {/* Persistent disclaimer banner at the top */}
        <div className="bg-amber-50 border-b border-amber-200 text-amber-800 text-xs text-center py-1.5 px-4">
          ⚕️ <strong>Research use only.</strong> This tool summarizes published literature and is
          not a substitute for professional medical advice, diagnosis, or treatment.
        </div>

        <div className="flex flex-col h-[calc(100vh-2rem)]">
          {/* Top navigation bar */}
          <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xl">🔬</span>
              <span className="font-semibold text-gray-800">Medical Literature Assistant</span>
            </div>
            <nav className="flex gap-4 text-sm text-gray-500">
              <a href="/" className="hover:text-blue-600">Chat</a>
              <a href="/history" className="hover:text-blue-600">History</a>
            </nav>
          </header>

          {/* Page content */}
          <main className="flex-1 overflow-hidden">{children}</main>
        </div>
      </body>
    </html>
  );
}
