from auth.password import verify_password, get_password_hash

# Test hash
saved_hash = "$2b$12$.xkfx.o1U59SMeWUILKW0uT7qJZHAdsg3RAH3gzQkh04adfLrZjMun"
password = "changeme"

print(f"Hash length: {len(saved_hash)}")
print(f"Hash: {saved_hash}")
print(f"Password: {password}")
print(f"Verification result: {verify_password(password, saved_hash)}")
