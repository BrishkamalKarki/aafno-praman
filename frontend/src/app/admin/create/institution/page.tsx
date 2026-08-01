import Link from "next/link";

import { CreateAccountForm, type AccountField } from "@/components/admin/create-account-form";
import { Icon } from "@/components/ui/icon";

export const metadata = { title: "Create an institution" };

const FIELDS: readonly AccountField[] = [
  { id: "legal_name", label: "Institution name", required: true },
  { id: "email", label: "Email", type: "email", required: true, autoComplete: "email" },
  {
    id: "registration_number",
    label: "UGC / registration number",
    required: true,
    help: "Checked against existing institutions — one number, one organisation.",
  },
  { id: "contact_person", label: "Registrar / contact name", autoComplete: "name" },
  { id: "phone", label: "Phone number", type: "tel", autoComplete: "tel" },
  { id: "website", label: "Website", type: "url", placeholder: "https://" },
  { id: "address", label: "Address", wide: true, placeholder: "Municipality, district" },
];

export default function CreateInstitutionPage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <Link
        href="/admin"
        className="inline-flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text"
      >
        <Icon name="chevron-right" size={12} className="rotate-180" />
        Back
      </Link>
      <h1 className="mt-2 text-lg font-semibold tracking-tight">Create an institution</h1>
      <p className="mt-1.5 max-w-lg text-sm text-text-muted">
        This sets up their issuer dashboard and registers them on the ledger in the same step.
        The platform generates and holds their signing key — nobody at the university installs a
        wallet or thinks about gas.
      </p>
      {/* Creating the account *is* the approval, so it is worth saying that the
          diligence is expected to have happened before this form is opened. */}
      <p className="mt-2 max-w-lg text-xs text-text-subtle">
        Creating an institution here approves it immediately. Check their accreditation before
        you do — everything they issue afterwards inherits its authority from this step.
      </p>

      <CreateAccountForm
        target="organization"
        fixedValues={{ kind: "INSTITUTION" }}
        fields={FIELDS}
        backHref="/admin"
        successNote="Their issuer dashboard is ready and their signing key is registered on chain. They can issue immediately."
      />
    </div>
  );
}
