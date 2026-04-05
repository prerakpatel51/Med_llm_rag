// page.tsx – main chat page (route: /)

import { ChatWindow } from "@/components/chat/ChatWindow";

export default function Home() {
  return (
    <div className="h-full">
      <ChatWindow />
    </div>
  );
}
