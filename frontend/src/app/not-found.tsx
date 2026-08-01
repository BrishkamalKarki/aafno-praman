import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardDescription, CardTitle } from "@/components/ui/card";

export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 items-center justify-center px-5 py-20">
      <Card raised className="w-full text-center">
        <CardBody className="flex flex-col items-center gap-4 pt-8">
          <p className="text-sm font-medium text-brand">404</p>
          <CardTitle className="text-xl">This page doesn&apos;t exist</CardTitle>
          <CardDescription className="max-w-sm">
            The link you followed points to a page that hasn&apos;t been built yet,
            or the address is wrong. Nothing on your account was affected.
          </CardDescription>
          <Link href="/" className="mt-2">
            <Button size="lg">Back to Aafno Praman</Button>
          </Link>
        </CardBody>
      </Card>
    </main>
  );
}
