import { NavLink } from "react-router-dom";

export interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

export function Nav({ items }: { items: NavItem[] }) {
  return (
    <nav aria-label="Primary" style={{ display: "flex", gap: 16 }}>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          style={({ isActive }) => ({
            fontSize: 14,
            color: isActive ? "#111827" : "#6b7280",
            fontWeight: isActive ? 600 : 500,
            textDecoration: "none",
            borderBottom: isActive ? "2px solid #111827" : "2px solid transparent",
            paddingBottom: 4,
          })}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
