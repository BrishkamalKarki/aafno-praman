import Link from "next/link";

import { CreateAccountForm, type AccountField } from "@/components/admin/create-account-form";
import { Icon } from "@/components/ui/icon";

export const metadata = { title: "Create a user" };

/**
 * The citizenship number is deliberately absent from this form.
 *
 * It may only be set by an approved issuer attesting to a number it already
 * holds on file — see `SeekerProfile`'s identity model. Collecting it here would
 * make the CITIZENSHIP identity level self-asserted by whoever typed it, which
 * is precisely what it exists to rule out. The registrar keeps it in their own
 * records; the platform learns it when a university issues against it.
 */
const FIELDS: readonly AccountField[] = [
  { id: "full_name", label: "Full name", required: true, autoComplete: "name" },
  { id: "email", label: "Email", type: "email", required: true, autoComplete: "email" },
  { id: "phone", label: "Phone number", type: "tel", autoComplete: "tel" },
  { id: "date_of_birth", label: "Date of birth", type: "date" },
  {
    id: "address",
    label: "Address",
    wide: true,
    placeholder: "Municipality, district",
  },
];

export default function CreateUserPage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <Link
        href="/admin"
        className="inline-flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text"
      >
        <Icon name="chevron-right" size={12} className="rotate-180" />
        Back
      </Link>
      <h1 className="mt-2 text-lg font-semibold tracking-tight">Create a user</h1>
      <p className="mt-1.5 max-w-lg text-sm text-text-muted">
        This sets up their citizen dashboard — credentials, share links, and who has checked
        them. They confirm any credential issued to them before it is ever anchored.
      </p>
      <p className="mt-2 max-w-lg text-xs text-text-subtle">
        Their citizenship number is not collected here. Only an approved institution can attest
        one, from records it already holds.
      </p>

      <CreateAccountForm
        target="user"
        fields={FIELDS}
        backHref="/admin"
        successNote="Their citizen dashboard is ready. Nothing is anchored until an institution issues them a credential and they confirm it."
      />
    </div>
  );
}
