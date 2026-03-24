import glob

files = glob.glob(r"c:\Users\prach\Documents\WIZDESK\LAST\frontend\*.html")
count = 0
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if r"'\${" in content:
        new_content = content.replace(r"'\${", "'${")
        with open(f, 'w', encoding='utf-8') as file:
            file.write(new_content)
        print(f"Fixed {f}")
        count += 1

print(f"Total files fixed: {count}")
